"""s6-r01: median asking price per m² by district from krisha.kz search pages.

The owner holds a development permission from Kolesa for automated access; without it this module must not run (п. 5.3).
Usage: python -m pipeline.price [pages_per_district]
Writes data/raw/krisha_prices.parquet (one row per listing card) and config/prices.yaml (median per district + date).
Polite: 1 request / 2 s, identifying User-Agent, search pages only (allowed by robots.txt), no phones, no personal data.
"""
import re, sys, time, datetime as dt
import pandas as pd, requests, yaml
from .common import ROOT, RAW, log

UA = "almaty-livemap/0.1 (development; permitted by Kolesa; github.com/t1mdurden/almaty-livemap)"
SLUGS = {
    "Алатауский район": "almaty-alatauskij", "Алмалинский район": "almaty-almalinskij", "Ауэзовский район": "almaty-auezovskiy",
    "Бостандыкский район": "almaty-bostandykskij", "Жетысуский район": "almaty-zhetysuskij", "Медеуский район": "almaty-medeuskij",
    "Наурызбайский район": "almaty-nauryzbajskiy", "Турксибский район": "almaty-turksibskij",
}
CARD = re.compile(r'<div class="a-card[^"]*"[^>]*data-id="(\d+)".*?a-card__title[^>]*>([^<]*)<.*?a-card__price[^>]*>([^<]*)<', re.S)

def parse(html):
    out = []
    for aid, title, price in CARD.findall(html):
        m = re.search(r"([\d.,]+)\s*м²", title); p = re.sub(r"[^\d]", "", price)
        if not m or not p:
            continue
        area = float(m.group(1).replace(",", ".")); tng = int(p)
        rooms = re.match(r"(\d+)-комнатная", title.strip())
        if area < 10 or tng < 1_000_000:
            continue
        out.append({"id": aid, "rooms": int(rooms.group(1)) if rooms else None, "area": area, "price": tng, "price_m2": round(tng / area)})
    return out

def main(pages=5):
    rows, counts = [], {}
    for district, slug in SLUGS.items():
        for page in range(1, pages + 1):
            url = f"https://krisha.kz/prodazha/kvartiry/{slug}/?page={page}"
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            title = re.search(r"<title>([^<]*)", r.text)
            if r.status_code != 200 or (title and "Казахстане" in title.group(1)):
                log(f"{district}: HTTP {r.status_code} / slug fell back to all-Kazakhstan on page {page}, stop"); break
            if page == 1:
                m = re.findall(r'"count":(\d+)', r.text); counts[district] = int(m[1]) if len(m) > 1 else None
            cards = parse(r.text)
            for c in cards:
                c.update({"district": district, "page": page})
            rows += cards
            time.sleep(2)
        log(f"{district}: {sum(1 for x in rows if x['district'] == district)} cards, listed total {counts.get(district)}")
    df = pd.DataFrame(rows).drop_duplicates("id")
    df.to_parquet(RAW / "krisha_prices.parquet", index=False)
    cfg = {"date": dt.date.today().isoformat(),
           "source": "krisha.kz search pages, median asking price per m² over the first pages (default sort)",
           "districts": {}}
    for d in SLUGS:
        sub = df[df.district == d]
        cfg["districts"][d] = {"price_m2": int(sub.price_m2.median()) if len(sub) else None, "n": int(len(sub)), "listed": counts.get(d)}
    (ROOT / "config" / "prices.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    print(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
