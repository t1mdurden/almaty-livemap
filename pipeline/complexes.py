"""ЖК (residential complexes) from krisha.kz complex pages — coordinates, class, developer, year, secondary price per m².
Owner holds a Kolesa development permission. Polite: 1 request / 2 s, search/complex pages only.

Usage: python -m pipeline.complexes crawl | grid
Output: data/raw/complexes.parquet, data/out/complexes.geojson, layers/complex.parquet (price_m2_zhk per hex = median over complexes in hex + ring 1)
"""
import re, sys, json, time, html, statistics
import h3, pandas as pd, requests
from .common import RAW, OUT, LAYERS, log

UA = "almaty-livemap/0.1 (development; permitted by Kolesa; github.com/t1mdurden/almaty-livemap)"
SITEMAP = "https://krisha.kz/sitemap/frontend/complexes.xml"
CACHE = RAW / "complexes"; CACHE.mkdir(exist_ok=True)

def urls():
    r = requests.get(SITEMAP, headers={"User-Agent": UA}, timeout=60); r.raise_for_status()
    return sorted(set(u for u in re.findall(r"https://krisha\.kz/complex/show/almaty/[^<\"]+/", r.text)))

def parse(s, url):
    out = {"url": url, "slug": url.rstrip("/").split("/")[-1]}
    t = re.search(r"<title>([^<]*)", s); out["title"] = html.unescape(t.group(1)).split(":")[0].strip() if t else None
    m = re.search(r'"map":\{"lat":([\d.]+),"lon":([\d.]+)', s)
    if m: out["lat"], out["lon"] = float(m.group(1)), float(m.group(2))
    # every <dt data-name=…>label</dt><dd>value</dd> pair of the parameters block
    params = {}
    for name, val in re.findall(r'<dt[^>]*data-name="([^"]+)"[^>]*>.*?</dt>\s*<dd[^>]*>(.*?)</dd>', s, re.S):
        params[name] = html.unescape(re.sub(r"<[^>]+>", " ", val)).strip()
    out["params"] = json.dumps(params, ensure_ascii=False)
    out["housing_class"] = params.get("housingClass"); out["building_type"] = params.get("buildingType") or params.get("houseType")
    for k in ("buildingYear", "year", "constructionYear", "deadline", "complexDate"):
        if params.get(k): out["year"] = params[k]; break
    mm = re.search(r'complex__sidebar-info-title">Застройщик</span>\s*</div>\s*<p[^>]*>(.*?)</p>', s, re.S)
    if mm: out["developer"] = html.unescape(re.sub(r"<[^>]+>", "", mm.group(1))).strip()
    own = s.split("complex-similar")[0]          # the "similar complexes" block carries other ЖК prices
    mm = re.search(r'от\s*([\d&nbsp;\s]+)<span class="currency-sign offer__currency">₸</span>\s*за м²', own)
    if mm: out["price_m2_from"] = int(re.sub(r"\D", "", mm.group(1)))
    # secondary-market listings embedded in the page: priceM2 for sell offers
    sell = re.search(r'"secondary":\{"sell":(\[.*?\]),"rent"', s, re.S)
    pm = []
    if sell:
        try:
            for a in json.loads(sell.group(1)):
                v = a.get("priceM2")
                if isinstance(v, (int, float)) and v > 100000: pm.append(v)
        except json.JSONDecodeError:
            pass
    pm += [int(x) for x in re.findall(r'"priceM2":(\d{6,8})', s)]
    pm = [p for p in pm if 150000 <= p <= 5000000]
    out["sec_n"] = len(pm); out["sec_price_m2"] = int(statistics.median(pm)) if pm else None
    return out

def crawl():
    us = urls(); log(f"{len(us)} Almaty complexes in sitemap")
    rows = []
    for i, u in enumerate(us):
        f = CACHE / (u.rstrip("/").split("/")[-1] + ".html")
        if not f.exists():
            r = requests.get(u, headers={"User-Agent": UA}, timeout=60)
            if r.status_code != 200: log(f"{u} → {r.status_code}"); time.sleep(5); continue
            f.write_text(r.text); time.sleep(2)
        rows.append(parse(f.read_text(), u))
        if i % 100 == 0: log(f"complexes: {i}/{len(us)}")
    df = pd.DataFrame(rows); df.to_parquet(RAW / "complexes.parquet", index=False)
    log(f"complexes parsed: {len(df)}, with coords {df.lat.notna().sum()}, with secondary price {df.sec_price_m2.notna().sum()}, with class {df.get('housing_class', pd.Series()).notna().sum()}")

def grid():
    df = pd.read_parquet(RAW / "complexes.parquet").dropna(subset=["lat", "lon"])
    df["h3"] = [h3.latlng_to_cell(a, b, 9) for a, b in zip(df.lat, df.lon)]
    df["price_m2"] = df.sec_price_m2.fillna(df.get("price_m2_from"))
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
              "properties": {k: (None if pd.isna(v) else v) for k, v in r._asdict().items() if k not in ("Index", "lat", "lon", "url")}} for r in df.itertuples()]
    (OUT / "complexes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    per = df.dropna(subset=["price_m2"]).groupby("h3")["price_m2"].apply(list).to_dict()
    g = pd.read_parquet(OUT / "grid.parquet"); out = []
    for c in g.h3:
        vals = []
        for n in h3.grid_disk(c, 1): vals += per.get(n, [])
        out.append({"h3": c, "price_m2_zhk": int(statistics.median(vals)) if vals else None, "zhk_n": len(vals)})
    pd.DataFrame(out).to_parquet(LAYERS / "complex.parquet", index=False)
    log(f"complex layer: {sum(1 for o in out if o['price_m2_zhk'])} hexes with a ЖК price within 1 ring")

if __name__ == "__main__":
    {"crawl": crawl, "grid": grid}[sys.argv[1] if len(sys.argv) > 1 else "crawl"]()
