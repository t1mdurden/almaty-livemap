"""Real stop -> routes data from the 2GIS Places API, looked up by the stop names OSM knows.

One request per distinct OSM stop name (~924), searched near the OSM position; items of type "station" with a `routes`
list are kept. Budget: Places API demo = 1000 requests per month, ~10 per minute. Cached per name in data/raw/stops2gis/.
Usage: python -m pipeline.stops2gis fetch | grid
"""
import sys, json, re, time, math
import h3, pandas as pd, requests
from .common import RAW, OUT, LAYERS, UA, log
from .reach import key

URL = "https://catalog.api.2gis.com/3.0/items"
CACHE = RAW / "stops2gis"; CACHE.mkdir(exist_ok=True)
PACE_S = 6.0


def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def fetch(limit=None):
    k = key()
    s = pd.read_parquet(RAW / "stops_routes.parquet").dropna(subset=["name"])
    s["name"] = s.name.str.strip()
    groups = s.groupby("name").agg(lat=("lat", "mean"), lon=("lon", "mean"), n=("lat", "size")).reset_index()
    spread = {n: max(_hav(g.lat.min(), g.lon.min(), g.lat.max(), g.lon.max()), 1) for n, g in s.groupby("name")}
    done = 0
    for r in groups.itertuples():
        f = CACHE / (re.sub(r"[^\w]+", "_", r.name)[:80] + ".json")
        if f.exists():
            continue
        if limit and done >= limit:
            break
        radius = int(min(3000, max(500, spread.get(r.name, 0) / 2 + 400)))
        p = {"q": r.name, "point": f"{r.lon:.6f},{r.lat:.6f}", "radius": radius, "type": "station",
             "fields": "items.point,items.routes,items.subtype", "page_size": 10, "key": k}
        try:
            rr = requests.get(URL, params=p, headers={"User-Agent": UA}, timeout=60).json()
        except Exception as ex:
            log(f"{r.name}: {ex}"); time.sleep(5); continue
        meta = rr.get("meta", {}); code = meta.get("code")
        if code == 200:
            items = [i for i in rr["result"]["items"] if i.get("type") == "station" and i.get("routes")]
        elif code == 404:
            items = []
        elif code == 429 or "too many" in json.dumps(meta).lower() or "limit" in json.dumps(meta).lower():
            log(f"{r.name}: rate limited ({meta}), waiting 65 s"); time.sleep(65); continue
        else:
            log(f"{r.name}: {meta}"); time.sleep(10); continue
        f.write_text(json.dumps({"name": r.name, "items": items}, ensure_ascii=False))
        done += 1
        if done % 50 == 0:
            log(f"stops2gis: {done} requests this run, cached {len(list(CACHE.glob('*.json')))} of {len(groups)}")
        time.sleep(PACE_S)
    log(f"stops2gis fetch done: +{done} requests; cached names {len(list(CACHE.glob('*.json')))} of {len(groups)}")


def grid():
    stops = {}
    for f in CACHE.glob("*.json"):
        for i in json.loads(f.read_text())["items"]:
            pt = i.get("point") or {}
            if "lat" not in pt:
                continue
            stops[i["id"]] = {"name": i.get("name"), "lat": pt["lat"], "lon": pt["lon"],
                              "routes": sorted({(x.get("subtype") or "bus", x.get("name")) for x in i["routes"] if x.get("name")})}
    sdf = pd.DataFrame(stops.values())
    sdf.to_parquet(RAW / "stops_2gis.parquet", index=False)
    log(f"2GIS stops: {len(sdf)} distinct, routes per stop median {sdf.routes.map(len).median()}")
    by_hex = {}
    for r in sdf.itertuples():
        c = h3.latlng_to_cell(r.lat, r.lon, 9)
        by_hex.setdefault(c, {"stops": 0, "routes": set()})
        by_hex[c]["stops"] += 1; by_hex[c]["routes"] |= set(r.routes)
    metro = pd.read_parquet(RAW / "metro_stations.parquet")
    metro_cells = {h3.latlng_to_cell(r.lat, r.lon, 9) for r in metro.itertuples()}
    # routes that serve the centre: any route with a stop within ~600 m of the destination
    import yaml
    dest = yaml.safe_load((OUT.parent.parent / "config" / "destinations.yaml").read_text())["destinations"][0]
    centre_routes = set()
    for r in sdf.itertuples():
        if _hav(r.lat, r.lon, dest["lat"], dest["lon"]) <= 600: centre_routes |= {x[1] for x in r.routes}
    log(f"routes serving the centre ({dest['name']}): {len(centre_routes)}")
    stop_pts = list(zip(sdf.lat, sdf.lon))
    g = pd.read_parquet(OUT / "grid.parquet"); out = []
    for row in g.itertuples():
        c = row.h3
        refs, n, refs300 = set(), 0, set()
        for kk in h3.grid_disk(c, 2):
            if kk in by_hex:
                refs |= by_hex[kk]["routes"]; n += by_hex[kk]["stops"]
        for kk in h3.grid_disk(c, 1):
            if kk in by_hex: refs300 |= by_hex[kk]["routes"]
        has_metro = any(kk in metro_cells for kk in h3.grid_disk(c, 4))
        names = sorted({x[1] for x in refs}, key=lambda x: (len(x), x))
        direct = sorted({x[1] for x in refs} & centre_routes, key=lambda x: (len(x), x))
        trolley = sum(1 for x in refs if x[0] == "trolleybus")
        d_stop = min((_hav(row.lat, row.lon, a, b) for a, b in stop_pts if abs(a - row.lat) < 0.02 and abs(b - row.lon) < 0.03), default=None)
        out.append({"h3": c, "routes_400m": len(names), "routes_250m": len({x[1] for x in refs300}), "stops_400m": n, "metro_800m": int(has_metro),
                    "trolleybus_400m": trolley, "pt_direct": len(direct), "direct_list": ", ".join(direct[:20]),
                    "stop_walk_min": round(d_stop * 1.3 / (5000 / 60), 1) if d_stop is not None else None,
                    "transit_proxy": len(names) + (8 if has_metro else 0), "route_list": ", ".join(names[:25])})
    df = pd.DataFrame(out); df.to_parquet(LAYERS / "transit.parquet", index=False)
    pop = pd.read_parquet(LAYERS / "pop.parquet"); m = df.merge(pop, on="h3"); m = m[m.pop_r8 >= 100]
    log(f"populated hexes: routes_400m median {m.routes_400m.median()}, >=1 route {(m.routes_400m > 0).mean():.0%}")
    c = h3.latlng_to_cell(43.2128, 76.8005, 9); row = df[df.h3 == c].iloc[0]
    log(f"Шугыла 340/3к15 hex: stops {row.stops_400m}, routes {row.routes_400m}: {row.route_list}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    {"fetch": lambda: fetch(int(sys.argv[2]) if len(sys.argv) > 2 else None), "grid": grid}[cmd]()
