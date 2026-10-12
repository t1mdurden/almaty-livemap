"""s1-r02: metro stations from OSM -> minutes on foot from each hex centre -> layers/metro.parquet"""
import math, json
import pandas as pd
from .common import OUT, LAYERS, RAW, overpass, bbox_str, log

WALK_M_PER_MIN = 5000 / 60
DETOUR = 1.3

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def stations() -> pd.DataFrame:
    q = f'[out:json][timeout:90][bbox:{bbox_str()}];node["station"="subway"];out;'
    d = overpass(q, cache="metro_stations.json")
    pts = [{"name": e["tags"].get("name"), "lat": e["lat"], "lon": e["lon"]} for e in d["elements"]]
    # dedupe entrances/duplicates: same name within 500 m
    keep = []
    for p in pts:
        if any(k["name"] == p["name"] and haversine_m(k["lat"], k["lon"], p["lat"], p["lon"]) < 500 for k in keep):
            continue
        keep.append(p)
    df = pd.DataFrame(keep)
    if len(df) < 11:
        raise SystemExit(f"only {len(df)} metro stations — Almaty has 11+; Overpass data incomplete")
    df.to_parquet(RAW / "metro_stations.parquet", index=False)
    return df

def main():
    grid = pd.read_parquet(OUT / "grid.parquet")
    st = stations()
    log("stations:", ", ".join(st["name"].astype(str)))
    out = []
    for r in grid.itertuples():
        d = min(haversine_m(r.lat, r.lon, s.lat, s.lon) for s in st.itertuples())
        out.append({"h3": r.h3, "metro_min": round(d * DETOUR / WALK_M_PER_MIN, 1)})
    df = pd.DataFrame(out)
    df.to_parquet(LAYERS / "metro.parquet", index=False)
    log(f"metro_min: min {df.metro_min.min()} median {df.metro_min.median()} max {df.metro_min.max()}")

if __name__ == "__main__":
    main()
