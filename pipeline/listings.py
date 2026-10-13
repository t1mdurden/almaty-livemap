"""All Almaty sale listings from krisha.kz search cards (owner holds a Kolesa development permission).
Usage: python -m pipeline.listings crawl [max_pages_per_district] | grid
crawl: per-district search pages (≤1000 pages each, 20 cards, 2 s pause) -> data/raw/listings.parquet (id, rooms, area, price, price_m2, address, district, seen)
grid:  match card addresses to OSM building addresses -> per-building price (buildings with ≥2 cards) + per-hex median -> layers/listing.parquet, data/out/listing_prices.json
"""
import re, sys, time, html, datetime as dt, statistics, json
import h3, pandas as pd, requests
from .common import RAW, OUT, LAYERS, log
from .price import SLUGS, UA

CACHE = RAW / "listings"; CACHE.mkdir(exist_ok=True)
CARD = re.compile(r'<div\s+data-id="(\d+)"[^>]*?(data-is-layout="1")?[^>]*class="a-card[^"]*"[^>]*>(.*?)(?=<div\s+data-id="|\Z)', re.S)

def parse_page(s):
    out = []
    for aid, layout, body in CARD.findall(s):
        if layout: continue
        t = re.search(r'a-card__title[^>]*>([^<]*)<', body); pr = re.search(r'a-card__price[^>]*>([^<]*)', body); sub = re.search(r'a-card__subtitle[^>]*>\s*([^<]*?)\s*</div>', body, re.S)
        if not (t and pr): continue
        m = re.search(r"([\d.,]+)\s*м²", t.group(1)); p = re.sub(r"\D", "", pr.group(1).replace("&nbsp;", ""))
        if not m or not p: continue
        area = float(m.group(1).replace(",", ".")); tng = int(p)
        if area < 10 or tng < 1_000_000: continue
        rooms = re.match(r"\s*(\d+)-комнатная", t.group(1))
        out.append({"id": aid, "rooms": int(rooms.group(1)) if rooms else None, "area": area, "price": tng, "price_m2": round(tng / area),
                    "address": html.unescape(re.sub(r"\s+", " ", sub.group(1))).strip() if sub else None})
    return out

def crawl(max_pages=1000):
    rows = []
    for district, slug in SLUGS.items():
        n_d = 0
        for page in range(1, max_pages + 1):
            f = CACHE / f"{slug}_{page}.html"
            if not f.exists():
                r = requests.get(f"https://krisha.kz/prodazha/kvartiry/{slug}/?page={page}", headers={"User-Agent": UA}, timeout=60)
                if r.status_code != 200: log(f"{slug} p{page}: HTTP {r.status_code}, stop"); break
                f.write_text(r.text); time.sleep(2)
            cards = parse_page(f.read_text())
            if not cards: break
            for c in cards: c.update({"district": district, "page": page})
            rows += cards; n_d += len(cards)
            if page % 50 == 0: log(f"{district}: page {page}, {n_d} cards")
        log(f"{district}: {n_d} cards")
    df = pd.DataFrame(rows).drop_duplicates("id"); df["seen"] = dt.date.today().isoformat()
    df.to_parquet(RAW / "listings.parquet", index=False)
    log(f"listings: {len(df)} unique cards")

ABBR = [(r"\bпросп(?:ект|\.)?\b", ""), (r"\bпр-т\b", ""), (r"\bул(?:ица|\.)?\b", ""), (r"\bбульвар\b|\bб-р\b", ""), (r"\bмкр\.?\b|\bмикрорайон\b|\bмассив\b", ""),
        (r"\bшоссе\b", ""), (r"\bпер(?:еулок|\.)?\b", ""), (r"\bдаңғылы\b|\bкөшесі\b|\bшағын ауданы\b", ""), (r"№\s*", ""), (r"[«»\"']", ""), (r"-й\b|-я\b|-е\b", ""), (r"\s+", " ")]
def norm(s):
    s = (s or "").lower().replace("ё", "е")
    for a, b in ABBR: s = re.sub(a, b, s)
    return s.strip(" ,.-")
def norm_house(h):
    h = (h or "").lower().replace(" ", "").replace("корпус", "к").replace("к.", "к")
    return re.sub(r"[^\w/]", "", h)

def grid():
    df = pd.read_parquet(RAW / "listings.parquet")
    # OSM buildings with addresses
    bl = json.loads((RAW / "all_buildings_center.json").read_text())["elements"]
    idx = {}
    for e in bl:
        t = e.get("tags", {}); c = e.get("center")
        if not c or not t.get("addr:street") or not t.get("addr:housenumber"): continue
        key = norm(t["addr:street"]) + " " + norm_house(t["addr:housenumber"])
        idx.setdefault(key, []).append((c["lat"], c["lon"], e["id"]))
    log(f"OSM addressed buildings: {len(idx)} distinct addresses")
    HOUSE = re.compile(r"^(.*?)[\s,]+(\d+[а-яa-z]?(?:\s*(?:/|к\.?|корпус\s*)\s*\d+[а-яa-z]?)?)$", re.I)
    def match(addr):
        if not addr: return None
        addr = addr.split(" — ")[0]                       # krisha appends a free-text comment after a dash
        parts = [p.strip() for p in addr.split(",")]
        cands = parts[1:] if len(parts) > 1 else parts    # drop the district
        tries = cands[::-1] + [" ".join(cands[-2:])] if len(cands) >= 2 else cands
        for cand in tries:
            m = HOUSE.match(cand.strip())
            if not m or not m.group(1).strip(): continue
            key = norm(m.group(1)) + " " + norm_house(m.group(2))
            if key in idx: return idx[key][0]
        return None
    hits = df.address.map(match)
    df["lat"] = hits.map(lambda x: x[0] if x else None); df["lon"] = hits.map(lambda x: x[1] if x else None); df["osm"] = hits.map(lambda x: x[2] if x else None)
    log(f"address match: {df.lat.notna().sum()} of {len(df)} cards ({df.lat.notna().mean():.0%})")
    m = df.dropna(subset=["lat"]).copy()
    m["h3"] = [h3.latlng_to_cell(a, b, 9) for a, b in zip(m.lat, m.lon)]
    per_b = m.groupby("osm").agg(price_m2=("price_m2", "median"), n=("id", "size")).query("n >= 2")
    per_h = m.groupby("h3")["price_m2"].apply(list).to_dict()
    g = pd.read_parquet(OUT / "grid.parquet"); out = []
    for c in g.h3:
        vals = []
        for n in h3.grid_disk(c, 1): vals += per_h.get(n, [])
        out.append({"h3": c, "price_m2_hex": int(statistics.median(vals)) if len(vals) >= 3 else None, "listing_n": len(vals)})
    pd.DataFrame(out).to_parquet(LAYERS / "listing.parquet", index=False)
    (OUT / "listing_prices.json").write_text(json.dumps({str(int(k)): {"p": int(v.price_m2), "n": int(v.n)} for k, v in per_b.iterrows()}))
    log(f"listing layer: {sum(1 for o in out if o['price_m2_hex'])} hexes with ≥3 priced cards within 1 ring; {len(per_b)} buildings with ≥2 cards")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "crawl"
    {"crawl": lambda: crawl(int(sys.argv[2]) if len(sys.argv) > 2 else 1000), "grid": grid}[cmd]()
