"""s4: travel time at 08:30 from every res-8 hex centre to the owner's destinations via 2GIS.

Usage: python -m pipeline.reach plan | car | pt | grid
- plan: print how many billable units car/pt need vs the demo-key cap and the 10k pack; makes NO requests
- car:  2GIS Distance Matrix (driving, traffic-aware at departure time), cached per (hex, destination)
- pt:   2GIS Routing /public_transport/2.0, one route per (hex, destination), cached
- grid: weighted mean minutes per res-8 hex -> spread to res-9 children -> layers/reach.parquet (car_min, pt_min)
Key: environment variable TWOGIS_KEY only. Never written to disk.
Body shapes verified against docs.2gis.com on 2026-10-12: Distance Matrix /get_dist_matrix?key&version=2.0 with points/sources/targets, "type":"statistics" + RFC3339 start_time (historical traffic), "transport":"driving"; Routing /public_transport/2.0 with source/target {point{lat,lon}}, transport[], unix start_time.
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
    if not k and (ROOT / ".env").exists():          # gitignored; value is never logged or written anywhere else
        for line in (ROOT / ".env").read_text().splitlines():
            if line.strip().startswith("TWOGIS_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not k:
        raise SystemExit("TWOGIS_KEY is not set (environment or almaty-livemap/.env)")
    return k

def next_weekday_0830() -> dt.datetime:
    """Next weekday 08:30 Almaty time (UTC+5) as an aware datetime."""
    tz = dt.timezone(dt.timedelta(hours=5))
    d = dt.datetime.now(tz) + dt.timedelta(days=1)
    while d.weekday() >= 5: d += dt.timedelta(days=1)
    return d.replace(hour=8, minute=30, second=0, microsecond=0)

def plan():
    o, d = origins(), destinations()
    pairs = len(o) * len(d)
    verdict = lambda n: "OK on demo key" if n <= DEMO_CAP else f"exceeds demo cap → 10k pack ({PACK10K_RUB} ₽/мес) or fewer destinations/res 7"
    print(f"origins (res {RES}, pop ≥ {MIN_POP}): {len(o)} | destinations: {len(d)} | pairs: {pairs}")
    print(f"with ONE destination (work only): {len(o)} units per API → {'fits the demo key' if len(o) <= DEMO_CAP else 'still over the demo cap'}")
    print(f"Distance Matrix (car): {pairs} units vs demo cap {DEMO_CAP} → {verdict(pairs)}")
    print(f"Routing public_transport (pt): {pairs} units vs demo cap {DEMO_CAP} → {verdict(pairs)}")
    print(f"cached: car {len([f for f in CACHE.glob('car_*.json') if not f.name.startswith('car_ev_')])}, pt {len(list(CACHE.glob('pt_*.json')))}, car evening {len(list(CACHE.glob('car_ev_*.json')))}")
    print(f"evening direction (centre → cell, 18:30) costs another {pairs} Distance Matrix units")

def _post(url, k, body, params=None):
    last = None
    for attempt in range(6):
        r = requests.post(url, params={"key": k, **(params or {})}, json=body, headers={"User-Agent": UA}, timeout=60)
        if r.status_code == 200:
            return r.json()
        last = f"HTTP {r.status_code}: {r.text[:160]}"
        if r.status_code in (429, 500, 502, 503, 504):
            log(f"2GIS retry {attempt + 1}: {last}"); time.sleep(5 * (attempt + 1)); continue
        raise SystemExit(f"2GIS {url} → {last}")
    raise SystemExit(f"2GIS: retries exhausted, last {last}")

def car():
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830()
    B = 10                            # demo key: matrix at most 10×10 (HTTP 403 above that); standard tariff allows 25
    for i in range(0, len(o), B):
        batch = [x for x in o[i:i + B] if not (CACHE / f"car_{x[0]}.json").exists()]
        if not batch: continue
        body = {"points": [{"lat": la, "lon": lo} for _, la, lo in batch] + [{"lat": x["lat"], "lon": x["lon"]} for x in d],
                "sources": list(range(len(batch))), "targets": list(range(len(batch), len(batch) + len(d))),
                "transport": "driving", "type": "statistics",
                "start_time": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        res = _post(DM_URL, k, body, {"version": "2.0"})
        by_src = {}
        for r in res.get("routes", []):
            if r.get("status", "OK") == "OK":
                by_src.setdefault(r["source_id"], {})[r["target_id"] - len(batch)] = r.get("duration")
        for j, (c, _, _) in enumerate(batch):
            (CACHE / f"car_{c}.json").write_text(json.dumps({"h3": c, "sec": by_src.get(j, {}), "t": t.isoformat()}))
        log(f"car: {min(i + B, len(o))}/{len(o)} origins")
        time.sleep(0.3)

def pt():
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830()
    for n, (c, la, lo) in enumerate(o):
        f = CACHE / f"pt_{c}.json"
        if f.exists(): continue
        sec = {}
        for j, x in enumerate(d):
            body = {"locale": "ru", "source": {"point": {"lat": la, "lon": lo}},
                    "target": {"point": {"lat": x["lat"], "lon": x["lon"]}},
                    "transport": ["bus", "trolleybus", "metro", "shuttle_bus", "light_rail"],
                    "start_time": int(t.timestamp()), "max_result_count": 3}
            res = _post(PT_URL, k, body)
            routes = res if isinstance(res, list) else res.get("routes", [])
            durs = [r.get("total_duration") for r in routes if r.get("total_duration")]
            sec[j] = min(durs) if durs else None
        f.write_text(json.dumps({"h3": c, "sec": sec, "t": t.isoformat()}))
        if n % 25 == 0: log(f"pt: {n}/{len(o)}")
        time.sleep(0.6)

def car_evening():
    """Reverse direction: from the destinations back to each cell at 18:30 on a weekday (evening jams).
    Same budget as `car` (1 unit per pair). Cached as car_ev_<h3>.json; layers get car_ev_min."""
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830().replace(hour=18, minute=30)
    B = 10
    for i in range(0, len(o), B):
        batch = [x for x in o[i:i + B] if not (CACHE / f"car_ev_{x[0]}.json").exists()]
        if not batch: continue
        body = {"points": [{"lat": x["lat"], "lon": x["lon"]} for x in d] + [{"lat": la, "lon": lo} for _, la, lo in batch],
                "sources": list(range(len(d))), "targets": list(range(len(d), len(d) + len(batch))),
                "transport": "driving", "type": "statistics",
                "start_time": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        res = _post(DM_URL, k, body, {"version": "2.0"})
        by_tgt = {}
        for r in res.get("routes", []):
            if r.get("status", "OK") == "OK":
                by_tgt.setdefault(r["target_id"] - len(d), {})[r["source_id"]] = r.get("duration")
        for j, (c, _, _) in enumerate(batch):
            (CACHE / f"car_ev_{c}.json").write_text(json.dumps({"h3": c, "sec": by_tgt.get(j, {}), "t": t.isoformat()}))
        log(f"car evening: {min(i + B, len(o))}/{len(o)}")
        time.sleep(0.3)

def pt_dm(limit=None):
    """PT travel time via Distance Matrix (transport=public_transport) — a second budget when /public_transport/2.0 returns 429."""
    k, o, d = key(), origins(), destinations()
    t = next_weekday_0830(); B = 10; done = 0
    todo = [x for x in o if not (CACHE / f"pt_{x[0]}.json").exists()]
    for i in range(0, len(todo), B):
        if limit and done >= limit: break
        batch = todo[i:i + B]
        body = {"points": [{"lat": la, "lon": lo} for _, la, lo in batch] + [{"lat": x["lat"], "lon": x["lon"]} for x in d],
                "sources": list(range(len(batch))), "targets": list(range(len(batch), len(batch) + len(d))),
                "transport": "public_transport", "start_time": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "public_transport_params": {"transport": ["bus", "trolleybus", "metro", "shuttle_bus", "light_rail"]}}
        res = _post(DM_URL, k, body, {"version": "2.0"})
        by_src = {}
        for r in res.get("routes", []):
            if r.get("status", "OK") == "OK":
                by_src.setdefault(r["source_id"], {})[r["target_id"] - len(batch)] = r.get("duration")
        for j, (c, _, _) in enumerate(batch):
            (CACHE / f"pt_{c}.json").write_text(json.dumps({"h3": c, "sec": by_src.get(j, {}), "t": t.isoformat(), "via": "distance_matrix"}))
        done += len(batch); log(f"pt via DM: {done}/{len(todo)}")
        time.sleep(0.5)

def grid():
    d = destinations(); w = [x.get("weight", 1) for x in d]
    rows = {}
    for mode in ("car", "pt", "car_ev"):
        for f in CACHE.glob(f"{mode}_*.json"):
            if mode == "car" and f.name.startswith("car_ev_"): continue
            j = json.loads(f.read_text())
            secs = [j["sec"].get(str(i)) for i in range(len(d))]
            if any(s is None for s in secs): continue
            rows.setdefault(j["h3"], {})[f"{mode}_min"] = round(sum(s / 60 * wi for s, wi in zip(secs, w)) / sum(w), 1)
    g = pd.read_parquet(OUT / "grid.parquet")
    g["h3_r8"] = [h3.cell_to_parent(c, RES) for c in g.h3]
    out = g[["h3"]].copy()
    for col in ("car_min", "pt_min", "car_ev_min"):
        out[col] = g.h3_r8.map({k: v.get(col) for k, v in rows.items()})
    if out.car_ev_min.notna().sum() == 0: out = out.drop(columns=["car_ev_min"])
    out.to_parquet(LAYERS / "reach.parquet", index=False)
    log(f"reach: car coverage {out.car_min.notna().mean():.0%}, pt coverage {out.pt_min.notna().mean():.0%}")

def probe():
    """Spend 1 unit on each API to verify request/response shapes before the full run."""
    k, d = key(), destinations()
    la, lo = 43.2392, 76.9468   # м. Абай
    t = next_weekday_0830()
    body = {"points": [{"lat": la, "lon": lo}, {"lat": d[0]["lat"], "lon": d[0]["lon"]}], "sources": [0], "targets": [1],
            "transport": "driving", "type": "statistics", "start_time": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    res = _post(DM_URL, k, body, {"version": "2.0"})
    print("DM:", json.dumps(res)[:300])
    body = {"locale": "ru", "source": {"point": {"lat": la, "lon": lo}}, "target": {"point": {"lat": d[0]["lat"], "lon": d[0]["lon"]}},
            "transport": ["bus", "trolleybus", "metro", "shuttle_bus", "light_rail"], "start_time": int(t.timestamp()), "max_result_count": 3}
    res = _post(PT_URL, k, body)
    routes = res if isinstance(res, list) else res.get("routes", [])
    print("PT:", type(res).__name__, len(routes), "routes; total_duration:", [r.get("total_duration") for r in routes][:3])

if __name__ == "__main__":
    {"plan": plan, "car": car, "car-evening": car_evening, "pt": pt, "pt-dm": lambda: pt_dm(), "grid": grid, "probe": probe}[sys.argv[1] if len(sys.argv) > 1 else "plan"]()
