#!/usr/bin/env bash
# s2 check: local crime rows == server count; station area worse than quiet residential; centre not auto-top by density.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m pipeline.crime count
uv run python -m pipeline.crime agg && uv run python -m pipeline.build
uv run python - <<'PY'
import json, h3
d = json.load(open('data/out/hexes.geojson'))
P = {f['properties']['h3']: f['properties'] for f in d['features']}
def at(lat, lon): return P[h3.latlng_to_cell(lat, lon, 9)]
station = at(43.2748, 76.9424)   # вокзал Алматы-2
orbita  = at(43.2075, 76.8835)   # Орбита-1, спальный район
erm     = at(43.1740, 76.9170)   # Ерменсай
print("crime_rate station", station['crime_rate'], "orbita", orbita['crime_rate'], "ermensay", erm['crime_rate'])
assert station['crime_rate'] is not None and erm['crime_rate'] is not None
assert station['crime_rate'] > erm['crime_rate'], "station should be worse than Ermensay"
assert station['crime_rate_p'] < erm['crime_rate_p']
rates = sorted([(p['crime_rate'], p) for p in P.values() if p['crime_rate'] is not None], key=lambda x: -x[0])
top = [p for _, p in rates[:max(1, len(rates)//20)]]
centre = lambda p: 43.235 <= h3.cell_to_latlng(p['h3'])[0] <= 43.28 and 76.90 <= h3.cell_to_latlng(p['h3'])[1] <= 76.96
share = sum(centre(p) for p in top) / len(top)
print(f"top-5% by crime_rate: {len(top)} hexes, centre share {share:.0%}")
assert share <= 0.5, share
print("s2 CHECK PASSED")
PY
