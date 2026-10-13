#!/usr/bin/env bash
# s8 check: reach from Абая/Байтурсынова covers ≥95% of built hexes in all three modes; ЖК facts on buildings; listing prices present.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python - <<'PY'
import json, yaml, pandas as pd
hx = json.load(open('data/out/hexes.geojson'))['features']; n = len(hx)
cov = lambda k: sum(1 for f in hx if f['properties'].get(k) is not None) / n
d = yaml.safe_load(open('config/destinations.yaml'))['destinations'][0]
print("destination:", d['name']); assert 'Байтурсынова' in d['name']
for k in ('car_min', 'pt_min', 'car_ev_min'):
    print(f"{k}: coverage {cov(k):.0%}"); assert cov(k) >= 0.95, k
b = json.load(open('data/out/buildings.geojson'))['features']
z = sum(1 for f in b if f['properties'].get('zhk')); print("buildings with ЖК:", z); assert z >= 1000
print("price_m2_zhk coverage", f"{cov('price_m2_zhk'):.0%}", "price_m2_hex coverage", f"{cov('price_m2_hex'):.0%}", "dtp_300m", f"{cov('dtp_300m'):.0%}", "pm25_recent", f"{cov('pm25_recent'):.0%}")
assert cov('price_m2_hex') >= 0.3 and cov('dtp_300m') >= 0.99
import h3
P = {f['properties']['h3']: f['properties'] for f in hx}
at = lambda la, lo: P[h3.latlng_to_cell(la, lo, 9)]
c = at(43.2386, 76.9275); print("car_min at centre:", c['car_min'], "pt_min:", c['pt_min']); assert c['car_min'] <= 6
print("s8 CHECK PASSED")
PY
