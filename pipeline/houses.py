"""Every building in the built-up area as a scored point, chunked for lazy loading.

Source: OSM way["building"] centroids (out center), ~265k in the bbox. Non-residential building types are dropped,
apartments are served separately as footprints (pipeline.buildings). Output: data/out/houses/<h3 res7>.geojson + index.json
(bbox per chunk) so the page loads only the chunks under the viewport from zoom 14.
"""
import json, math
import h3, numpy as np, pandas as pd
from .common import RAW, OUT, overpass, bbox_str, log
from .metro import haversine_m, WALK_M_PER_MIN, DETOUR

NONRES = {"apartments", "commercial", "industrial", "retail", "warehouse", "garage", "garages", "shed", "office", "school", "kindergarten",
          "hospital", "university", "college", "church", "mosque", "cathedral", "chapel", "temple", "public", "government", "hotel", "service",
          "transportation", "train_station", "hangar", "roof", "greenhouse", "barn", "stable", "construction", "ruins", "sports_hall",
          "sports_centre", "stadium", "parking", "carport", "kiosk", "supermarket", "fire_station", "civic", "hut", "cabin", "toilets",
          "farm_auxiliary", "cowshed", "military", "bunker", "tower", "water_tower", "transformer_tower", "gatehouse", "pavilion", "grandstand"}
DIR = OUT / "houses"

def main():
    d = overpass(f'[out:json][timeout:300][bbox:{bbox_str()}];(way["building"];);out center tags;', cache="all_buildings_center.json")
    hexes = {f["properties"]["h3"]: f["properties"] for f in json.load(open(OUT / "hexes.geojson"))["features"]}
    st = pd.read_parquet(RAW / "metro_stations.parquet"); stations = list(zip(st.lat, st.lon))
    dist = np.sort(np.array([p["metro_min"] for p in hexes.values() if isinstance(p.get("metro_min"), (int, float))]))
    chunks, n_in, n_type, n_out = {}, 0, 0, 0
    for e in d["elements"]:
        c = e.get("center"); t = e.get("tags", {})
        if not c: continue
        if t.get("building") in NONRES or t.get("amenity") or t.get("shop") or t.get("office"): n_type += 1; continue
        h = h3.latlng_to_cell(c["lat"], c["lon"], 9)
        if h not in hexes: n_out += 1; continue
        m = min(haversine_m(c["lat"], c["lon"], a, b) for a, b in stations) * DETOUR / WALK_M_PER_MIN
        mp = 1 - np.searchsorted(dist, m) / len(dist)
        pr = {"h3": h, "mm": round(m, 1), "mp": round(float(mp), 3)}
        addr = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
        if addr: pr["a"] = addr
        if t.get("building:levels"): pr["lv"] = t["building:levels"]
        if t.get("building") not in (None, "yes", "house", "detached", "residential"): pr["t"] = t["building"]
        chunks.setdefault(h3.cell_to_parent(h, 7), []).append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(c["lon"], 5), round(c["lat"], 5)]}, "properties": pr})
        n_in += 1
    DIR.mkdir(exist_ok=True)
    for f in DIR.glob("*.geojson"): f.unlink()
    index = []
    for r7, feats in chunks.items():
        lons = [f["geometry"]["coordinates"][0] for f in feats]; lats = [f["geometry"]["coordinates"][1] for f in feats]
        (DIR / f"{r7}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
        index.append({"id": r7, "n": len(feats), "bbox": [min(lons), min(lats), max(lons), max(lats)]})
    (DIR / "index.json").write_text(json.dumps(index))
    total_mb = sum(f.stat().st_size for f in DIR.glob("*.geojson")) / 1e6
    log(f"houses: {n_in} kept in {len(chunks)} chunks ({total_mb:.1f} MB); dropped {n_type} non-residential, {n_out} outside built hexes")

if __name__ == "__main__":
    main()
