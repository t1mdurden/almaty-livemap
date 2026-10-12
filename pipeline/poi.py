"""s5: daily-life POI from OSM -> per-hex counts within 1 km and cat15 (categories present out of 6)

Usage: python -m pipeline.poi fetch | grid
"""
import sys
import h3, pandas as pd
from .common import RAW, OUT, LAYERS, overpass, bbox_str, log

CATS = {
    "grocery":  'nwr["shop"~"^(supermarket|convenience|greengrocer|grocery)$"]',
    "pharmacy": 'nwr["amenity"="pharmacy"]',
    "school":   'nwr["amenity"="school"]',
    "kindergarten": 'nwr["amenity"="kindergarten"]',
    "clinic":   'nwr["amenity"~"^(clinic|doctors|hospital)$"]',
    "park":     'nwr["leisure"~"^(park|garden|playground)$"]',
}
RADIUS_RINGS = 6   # H3 res 9 edge ≈ 174 m → 6 rings ≈ 1 km

def fetch():
    frames = []
    for cat, sel in CATS.items():
        q = f"[out:json][timeout:120][bbox:{bbox_str()}];({sel};);out center tags;"
        d = overpass(q, cache=f"poi_{cat}.json")
        rows = []
        for e in d["elements"]:
            lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
            if lat is None: continue
            rows.append({"cat": cat, "osm": f"{e['type']}/{e['id']}", "name": e.get("tags", {}).get("name"), "lat": lat, "lon": lon})
        log(f"{cat}: {len(rows)}")
        frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(RAW / "poi.parquet", index=False)
    print(df.cat.value_counts().to_string())

def grid():
    poi = pd.read_parquet(RAW / "poi.parquet")
    poi["h3"] = [h3.latlng_to_cell(la, lo, 9) for la, lo in zip(poi.lat, poi.lon)]
    per = poi.groupby(["h3", "cat"]).size().unstack(fill_value=0)
    idx = per.to_dict("index")
    g = pd.read_parquet(OUT / "grid.parquet")
    out = []
    for c in g.h3:
        row = {"h3": c}
        disk = h3.grid_disk(c, RADIUS_RINGS)
        for cat in CATS:
            row[f"poi_{cat}"] = int(sum(idx[n][cat] for n in disk if n in idx))
        row["cat15"] = sum(1 for cat in CATS if row[f"poi_{cat}"] > 0)
        out.append(row)
    df = pd.DataFrame(out)
    df.to_parquet(LAYERS / "poi.parquet", index=False)
    log(f"cat15 distribution: {df.cat15.value_counts().sort_index().to_dict()}")

if __name__ == "__main__":
    {"fetch": fetch, "grid": grid}[sys.argv[1] if len(sys.argv) > 1 else "fetch"]()
