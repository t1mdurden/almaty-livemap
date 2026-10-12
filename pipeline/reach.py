"""s4: travel time at 08:30 from every res-8 hex centre to the owner's destinations via 2GIS.

Usage: python -m pipeline.reach plan | car | pt | grid
- plan: print how many billable units car/pt need vs the demo-key cap and the 10k pack; makes NO requests
- car:  2GIS Distance Matrix (driving, traffic-aware at departure time), cached per (hex, destination)
- pt:   2GIS Routing /public_transport/2.0, one route per (hex, destination), cached
- grid: weighted mean minutes per res-8 hex -> spread to res-9 children -> layers/reach.parquet (car_min, pt_min)
Key: environment variable TWOGIS_KEY only. Never written to disk.
Endpoints/body shapes follow docs.2gis.com (Distance Matrix, Routing public transport) and are unverified until the first keyed run.
"""
import sys, os, json, time, datetime as dt
import h3, pandas as pd, requests, yaml
from .common import ROOT, RAW, OUT, LAYERS, UA, log

CFG = ROOT / "config" / "destinations.yaml"
CACHE = RAW / "reach"; CACHE.mkdir(exist_ok=True)
DEMO_CAP = 1000                 # per API, docs.2gis.com platform-manager pricing, read 2026-10-12
PACK10K_RUB = 6700
DM_URL = "https://routing.api.2gis.com/get_dist_matrix"
PT_URL = "https://routing.api.2gis.com/public_transport/2.0"
RES = 8

def destinations():
    if not CFG.exists():
        raise SystemExit(f"{CFG} missing — copy config/destinations.example.yaml and fill in your points")
    d = yaml.safe_load(CFG.read_text())["destinations"]
    if not d:
        raise SystemExit("destinations.yaml has 0 points")
    return d

MIN_POP = 100   # res-8 cells with fewer residents are steppe/industry — no one chooses a flat there

def origins():
    pop = pd.read_parquet(LAYERS / "pop.parquet")
    r8 = sorted(set(pop.loc[pop.pop_r8 >= MIN_POP, "h3_r8"]))
    return [(c, *h3.cell_to_latlng(c)) for c in r8]

def key():
    k = os.environ.get("TWOGIS_KEY")
    if not k:
        raise SystemExit("TWOGIS_KEY is not set in the environment")
    return k

def next_weekday_0830():
    d = dt.datetime.now() + dt.timedelta(days=1)
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    return int(d.replace(hour=8, minute=30, second=0, microsecond=0).timestamp())

def plan():
    o, d = origins(), destinations()
    pairs = len(o) * len(d)
    verdict = lambda n: "OK on demo key" if n <= DEMO_CAP else f"exceeds demo cap → 10k pack ({PACK10K_RUB} ₽/мес) or fewer destinations/res 7"
    print(f"origins (res {RES}, pop ≥ {MIN_POP}): {len(o)} | destinations: {len(d)} | pairs: {pairs}")
    print(f"with ONE destination (work only): {len(o)} units per API → {'fits the demo key' if len(o) <= DEMO_CAP else 'still over the demo cap'}")
    print(f"Distance Matrix (car): {pairs} units vs demo cap {DEMO_CAP} → {verdict(pairs)}")
    print(f"Routing public_transport (pt): {pairs} units vs demo cap {DEMO_CAP} → {verdict(pairs)}")
    print(f"cached: car {len(list(CACHE.glob('car_*.json')))}, pt {len(list(CACHE.glob('pt_*.json')))}")

def _post(url, k, body):
    for attempt in range(4):
        r = requests.post(url, params={"key": k}, json=body, headers={"User-Agent": UA}, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503):
            time.sleep(3 * (attempt + 1)); continue
        raise SystemExit(f"2GIS {url} → HTTP {r.status_code}: {r.text[:200]}")
    raise SystemExit("2GIS: retries exhausted")

def car():
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830()
    for i in range(0, len(o), 25):   # 25 points per side is the standard-tariff limit
        batch = [x for x in o[i:i + 25] if not (CACHE / f"car_{x[0]}.json").exists()]
        if not batch: continue
        body = {"points": [{"lat": la, "lon": lo} for _, la, lo in batch] + [{"lat": x["lat"], "lon": x["lon"]} for x in d],
                "sources": list(range(len(batch))), "targets": list(range(len(batch), len(batch) + len(d))),
                "type": "jam", "start_time": t}
        res = _post(DM_URL, k, body)
        by_src = {}
        for r in res.get("routes", []):
            by_src.setdefault(r["source_id"], {})[r["target_id"] - len(batch)] = r.get("duration")
        for j, (c, _, _) in enumerate(batch):
            (CACHE / f"car_{c}.json").write_text(json.dumps({"h3": c, "sec": by_src.get(j, {}), "t": t}))
        log(f"car: {min(i + 25, len(o))}/{len(o)} origins")
        time.sleep(0.3)

def pt():
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830()
    for n, (c, la, lo) in enumerate(o):
        f = CACHE / f"pt_{c}.json"
        if f.exists(): continue
        sec = {}
        for j, x in enumerate(d):
            body = {"locale": "ru", "source": {"name": "A", "point": {"lat": la, "lon": lo}},
                    "target": {"name": "B", "point": {"lat": x["lat"], "lon": x["lon"]}},
                    "transport": ["bus", "trolleybus", "metro", "shuttle_bus", "tram", "light_rail"],
                    "start_time": t}
            res = _post(PT_URL, k, body)
            routes = res if isinstance(res, list) else res.get("routes", [])
            durs = [r.get("total_duration") for r in routes if r.get("total_duration")]
            sec[j] = min(durs) if durs else None
        f.write_text(json.dumps({"h3": c, "sec": sec, "t": t}))
        if n % 25 == 0: log(f"pt: {n}/{len(o)}")
        time.sleep(0.2)

def grid():
    d = destinations(); w = [x.get("weight", 1) for x in d]
    rows = {}
    for mode in ("car", "pt"):
        for f in CACHE.glob(f"{mode}_*.json"):
            j = json.loads(f.read_text())
            secs = [j["sec"].get(str(i)) for i in range(len(d))]
            if any(s is None for s in secs): continue
            rows.setdefault(j["h3"], {})[f"{mode}_min"] = round(sum(s / 60 * wi for s, wi in zip(secs, w)) / sum(w), 1)
    g = pd.read_parquet(OUT / "grid.parquet")
    g["h3_r8"] = [h3.cell_to_parent(c, RES) for c in g.h3]
    out = g[["h3"]].copy()
    for col in ("car_min", "pt_min"):
        out[col] = g.h3_r8.map({k: v.get(col) for k, v in rows.items()})
    out.to_parquet(LAYERS / "reach.parquet", index=False)
    log(f"reach: car coverage {out.car_min.notna().mean():.0%}, pt coverage {out.pt_min.notna().mean():.0%}")

if __name__ == "__main__":
    {"plan": plan, "car": car, "pt": pt, "grid": grid}[sys.argv[1] if len(sys.argv) > 1 else "plan"]()
