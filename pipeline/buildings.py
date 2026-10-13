"""Buildings with their own metro walk time plus their hex's other factors.
- data/out/buildings.geojson: apartment footprints (building=apartments)
- data/out/houses.geojson: every other residential building as a point (house/detached/residential/…), ~70k
Each feature carries h3, own metro_min (+ its percentile against the built-hex distribution), address if OSM has it.
Score is computed in the browser from the hex's percentiles + the building's own metro percentile."""
import json, math
import h3, numpy as np, pandas as pd
from .common import RAW, OUT, log
from .metro import haversine_m, WALK_M_PER_MIN, DETOUR

def main():
    hexes = {f["properties"]["h3"]: f["properties"] for f in json.load(open(OUT / "hexes.geojson"))["features"]}
    st = pd.read_parquet(RAW / "metro_stations.parquet")
    stations = list(zip(st.lat, st.lon))
    dist = np.sort(np.array([p["metro_min"] for p in hexes.values() if isinstance(p.get("metro_min"), (int, float))]))
    def metro(lat, lon):
        m = min(haversine_m(lat, lon, a, b) for a, b in stations) * DETOUR / WALK_M_PER_MIN
        p = 1 - np.searchsorted(dist, m) / len(dist)          # share of built hexes that are farther
        return round(m, 1), round(float(p), 3)
    def props(e, lat, lon):
        c = h3.latlng_to_cell(lat, lon, 9)
        if c not in hexes: return None
        t = e.get("tags", {})
        m, mp = metro(lat, lon)
        out = {"h3": c, "mm": m, "mp": mp}
        addr = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
        if addr: out["a"] = addr
        if t.get("building:levels"): out["lv"] = t["building:levels"]
        if t.get("name"): out["n"] = t["name"]
        return out
    # nearest ЖК within 120 m (krisha complexes), if crawled
    zhk = []
    cf = RAW / "complexes.parquet"
    if cf.exists():
        cdf = pd.read_parquet(cf).dropna(subset=["lat", "lon"])
        zhk = [(r.lat, r.lon, r.title.replace(" Алматы", ""), r.housing_class, r.developer, r.sec_price_m2) for r in cdf.itertuples()]
    def nearest_zhk(lat, lon):
        best = None
        for la, lo, name, cls, dev, pm in zhk:
            if abs(la - lat) > 0.002 or abs(lo - lon) > 0.003: continue
            dd = haversine_m(lat, lon, la, lo)
            if dd <= 120 and (best is None or dd < best[0]): best = (dd, name, cls, dev, pm)
        return best
    # apartments: polygons
    apts = json.loads((RAW / "apartments.json").read_text())["elements"]
    feats = []
    for e in apts:
        g = e.get("geometry")
        if not g or len(g) < 4: continue
        lat = sum(p["lat"] for p in g) / len(g); lon = sum(p["lon"] for p in g) / len(g)
        pr = props(e, lat, lon)
        if pr is None: continue
        z = nearest_zhk(lat, lon)
        if z: pr.update({"zhk": z[1], "zcls": z[2], "zdev": z[3], "zpm": None if pd.isna(z[4]) else int(z[4])})
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[p["lon"], p["lat"]] for p in g]]}, "properties": pr})
    (OUT / "buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    log(f"apartments: {len(feats)} footprints, {round((OUT/'buildings.geojson').stat().st_size/1e6,1)} MB")
    return
    hs = json.loads((RAW / "houses_center.json").read_text())["elements"]
    pts = []
    for e in hs:
        c = e.get("center")
        if not c: continue
        pr = props(e, c["lat"], c["lon"])
        if pr is None: continue
        pts.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(c["lon"], 5), round(c["lat"], 5)]}, "properties": pr})
    (OUT / "houses.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": pts}, ensure_ascii=False, separators=(",", ":")))
    log(f"houses: {len(pts)} points, {round((OUT/'houses.geojson').stat().st_size/1e6,1)} MB")

if __name__ == "__main__":
    main()
