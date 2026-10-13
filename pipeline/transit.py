"""Transit proxy from OSM, route-geometry based.

OSM Almaty has 2019 bus stops but only a few hundred are linked to route relations, so instead of relation membership a stop is
served by every bus/trolleybus route whose line passes within SNAP_M of it. Per hex: distinct routes with a stop within 400 m,
number of stops within 400 m, metro within 800 m. Usage: python -m pipeline.transit
"""
import json, math
import h3, pandas as pd
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from .common import RAW, OUT, LAYERS, overpass, bbox_str, log

STOP_RINGS, METRO_RINGS = 2, 4      # ≈400 m, ≈800 m at res 9
SNAP_M = 30

def main():
    q = f'[out:json][timeout:180][bbox:{bbox_str()}];relation["route"~"^(bus|trolleybus)$"]->.r;.r out body;way(r.r);out geom;'
    d = overpass(q, cache="transit_routes_geom.json")
    ways = {e["id"]: [(p["lon"], p["lat"]) for p in e.get("geometry", [])] for e in d["elements"] if e["type"] == "way"}
    routes = []   # (ref, LineString segments)
    for r in (e for e in d["elements"] if e["type"] == "relation"):
        ref = r["tags"].get("ref") or f"rel{r['id']}"
        segs = [LineString(ways[m["ref"]]) for m in r["members"] if m["type"] == "way" and len(ways.get(m["ref"], [])) >= 2]
        if segs: routes.append((ref, segs))
    seg_list, seg_ref = [], []
    for ref, segs in routes:
        for sgm in segs: seg_list.append(sgm); seg_ref.append(ref)
    tree = STRtree(seg_list)
    stops = json.loads((RAW / "stops_all.json").read_text())["elements"]
    deg = SNAP_M / 111000.0
    stop_rows = []
    for e in stops:
        t = e.get("tags", {})
        if not (t.get("highway") == "bus_stop" or t.get("public_transport") == "platform"): continue
        lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None: continue
        pt = Point(lon, lat)
        refs = {seg_ref[i] for i in tree.query(pt.buffer(deg * 1.5)) if seg_list[i].distance(pt) <= deg * 1.5}
        stop_rows.append({"name": t.get("name"), "lat": lat, "lon": lon, "h3": h3.latlng_to_cell(lat, lon, 9), "routes": sorted(refs, key=lambda x: (len(x), x))})
    sdf = pd.DataFrame(stop_rows); sdf.to_parquet(RAW / "stops_routes.parquet", index=False)
    log(f"routes with geometry: {len(routes)} ({len({r for r,_ in routes})} refs); stops: {len(sdf)}, with ≥1 route by proximity: {(sdf.routes.map(len)>0).sum()}")
    by_hex = {}
    for r in sdf.itertuples():
        by_hex.setdefault(r.h3, {"stops": 0, "routes": set()})
        by_hex[r.h3]["stops"] += 1; by_hex[r.h3]["routes"] |= set(r.routes)
    metro = pd.read_parquet(RAW / "metro_stations.parquet")
    metro_cells = {h3.latlng_to_cell(r.lat, r.lon, 9) for r in metro.itertuples()}
    g = pd.read_parquet(OUT / "grid.parquet"); out = []
    for c in g.h3:
        refs, stops_n = set(), 0
        for n in h3.grid_disk(c, STOP_RINGS):
            if n in by_hex: refs |= by_hex[n]["routes"]; stops_n += by_hex[n]["stops"]
        has_metro = any(n in metro_cells for n in h3.grid_disk(c, METRO_RINGS))
        out.append({"h3": c, "routes_400m": len(refs), "stops_400m": stops_n, "metro_800m": int(has_metro),
                    "transit_proxy": len(refs) + (8 if has_metro else 0), "route_list": ", ".join(sorted(refs, key=lambda x: (len(x), x))[:20])})
    df = pd.DataFrame(out); df.to_parquet(LAYERS / "transit.parquet", index=False)
    pop = pd.read_parquet(LAYERS / "pop.parquet"); m = df.merge(pop, on="h3"); m = m[m.pop_r8 >= 100]
    log(f"populated hexes: routes_400m median {m.routes_400m.median()}, ≥1 route {(m.routes_400m>0).mean():.0%}, stops_400m median {m.stops_400m.median()}")
    c = h3.latlng_to_cell(43.2128, 76.8005, 9); row = df[df.h3 == c].iloc[0]
    log(f"Шугыла 340/3к15 hex: stops {row.stops_400m}, routes {row.routes_400m}: {row.route_list}")

if __name__ == "__main__":
    main()
