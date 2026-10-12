"""s4-r05: free transit proxy from OSM — distinct bus/trolleybus routes with a stop within 400 m + metro bonus.

Usage: python -m pipeline.transit
"""
import math
import h3, pandas as pd
from .common import RAW, OUT, LAYERS, overpass, bbox_str, log

STOP_RINGS = 2      # res 9 edge ≈ 174 m → 2 rings ≈ 400 m
METRO_RINGS = 4     # ≈ 800 m

def main():
    q = f'[out:json][timeout:120][bbox:{bbox_str()}];relation["route"~"^(bus|trolleybus)$"];out body;node(r);out skel;'
    d = overpass(q, cache="transit_routes.json")
    rels = [e for e in d["elements"] if e["type"] == "relation"]
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in d["elements"] if e["type"] == "node"}
    stop_routes = {}   # h3 -> set(route ref)
    for r in rels:
        ref = r["tags"].get("ref") or f"rel{r['id']}"
        for m in r["members"]:
            if m["type"] == "node" and m["ref"] in nodes and ("stop" in m.get("role", "") or "platform" in m.get("role", "") or m.get("role") == ""):
                la, lo = nodes[m["ref"]]
                stop_routes.setdefault(h3.latlng_to_cell(la, lo, 9), set()).add(ref)
    metro = pd.read_parquet(RAW / "metro_stations.parquet")
    metro_cells = {h3.latlng_to_cell(r.lat, r.lon, 9) for r in metro.itertuples()}
    g = pd.read_parquet(OUT / "grid.parquet")
    out = []
    for c in g.h3:
        refs = set()
        for n in h3.grid_disk(c, STOP_RINGS):
            refs |= stop_routes.get(n, set())
        has_metro = any(n in metro_cells for n in h3.grid_disk(c, METRO_RINGS))
        out.append({"h3": c, "routes_400m": len(refs), "metro_800m": int(has_metro), "transit_proxy": len(refs) + (8 if has_metro else 0)})
    df = pd.DataFrame(out)
    df.to_parquet(LAYERS / "transit.parquet", index=False)
    log(f"transit: {len(rels)} route relations, {len(stop_routes)} stop hexes; routes_400m median {df.routes_400m.median()} max {df.routes_400m.max()}; metro hexes {df.metro_800m.sum()}")

if __name__ == "__main__":
    main()
