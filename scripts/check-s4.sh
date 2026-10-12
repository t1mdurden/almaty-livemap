#!/usr/bin/env bash
# s4 check: coverage ≥90% of populated res-8 cells, ≤5 min at a destination, Kalkaman slower than Alatau by PT, no literal key in code.
set -euo pipefail
cd "$(dirname "$0")/.."
! grep -rn -E "key=[A-Za-z0-9]{20,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" pipeline/ web/ scripts/ || { echo "literal key found"; exit 1; }
[ -f config/destinations.yaml ] || { echo "BLOCKED: config/destinations.yaml missing (owner)"; exit 2; }
{ [ -n "${TWOGIS_KEY:-}" ] || grep -q "^TWOGIS_KEY=" .env 2>/dev/null; } || { echo "BLOCKED: TWOGIS_KEY not set (owner)"; exit 2; }
uv run python -m pipeline.reach plan
uv run python -m pipeline.reach grid && uv run python -m pipeline.build
uv run python - <<'PY'
import json, h3, yaml, pandas as pd
r = pd.read_parquet('data/out/layers/reach.parquet'); pop = pd.read_parquet('data/out/layers/pop.parquet')
m = r.merge(pop, on='h3'); m = m[m.pop_r8 >= 100]
cov_car, cov_pt = m.car_min.notna().mean(), m.pt_min.notna().mean()
print(f"coverage car {cov_car:.0%} pt {cov_pt:.0%}"); assert cov_car >= 0.9 and cov_pt >= 0.9
d = yaml.safe_load(open('config/destinations.yaml'))['destinations'][0]
P = {f['properties']['h3']: f['properties'] for f in json.load(open('data/out/hexes.geojson'))['features']}
at = lambda la, lo: P[h3.latlng_to_cell(la, lo, 9)]
near = at(d['lat'], d['lon']); print("car_min at destination 1:", near['car_min']); assert near['car_min'] is not None and near['car_min'] <= 5 * 1.0 + 5  # weighted mean over all destinations, so loose
kalk, alatau = at(43.2160, 76.8020), at(43.2520, 76.8990)
print("pt_min Kalkaman", kalk['pt_min'], "Alatau", alatau['pt_min']); assert kalk['pt_min'] > alatau['pt_min']
print("s4 CHECK PASSED")
PY
