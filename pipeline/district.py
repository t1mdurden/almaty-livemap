"""s6-r01: Almaty districts (OSM admin_level 6) -> district name per hex + price_m2 from config/prices.yaml -> layers/district.parquet"""
import yaml, pandas as pd
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from .common import ROOT, OUT, LAYERS, overpass, bbox_str, log

PRICES = ROOT / "config" / "prices.yaml"

def districts():
    q = f'[out:json][timeout:120][bbox:{bbox_str()}];relation["boundary"="administrative"]["admin_level"="6"];out geom;'
    d = overpass(q, cache="districts.json")
    polys = {}
    for r in d["elements"]:
        name = r["tags"].get("name:ru") or r["tags"].get("name")
        if "район" not in (name or "") and "ауданы" not in (name or ""): continue
        from shapely.geometry import LineString, Polygon
        from shapely.ops import polygonize, linemerge
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in r["members"] if m["type"] == "way" and m.get("role") == "outer" and "geometry" in m]
        merged = linemerge(lines)
        poly = unary_union(list(polygonize(merged)))
        if poly.is_empty: continue
        polys[name.replace(" ауданы", " район")] = poly
    return polys

def main():
    polys = districts()
    log("districts:", ", ".join(polys))
    prices = yaml.safe_load(PRICES.read_text()) if PRICES.exists() else {}
    pm2 = {k: v.get("price_m2") for k, v in (prices.get("districts") or {}).items()}
    g = pd.read_parquet(OUT / "grid.parquet")
    names = []
    for r in g.itertuples():
        pt = Point(r.lon, r.lat)
        names.append(next((n for n, p in polys.items() if p.contains(pt)), None))
    g["district"] = names
    g["price_m2"] = g.district.map(pm2)
    g["price_date"] = prices.get("date")
    g[["h3", "district", "price_m2", "price_date"]].to_parquet(LAYERS / "district.parquet", index=False)
    log(f"district coverage {g.district.notna().mean():.0%}; priced {g.price_m2.notna().mean():.0%}; {g.district.value_counts().to_dict()}")

if __name__ == "__main__":
    main()
