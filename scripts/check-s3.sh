#!/usr/bin/env bash
# s3 check: ≥15 sensors with a winter mean; upper city cleaner than lower city; data period shown on the page.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m pipeline.air sensors && uv run python -m pipeline.air history && uv run python -m pipeline.air grid && uv run python -m pipeline.build
uv run python - <<'PY'
import json, h3, pandas as pd
w = pd.read_parquet('data/raw/air_winter.parquet'); print("sensors with winter mean:", len(w)); assert len(w) >= 15
d = json.load(open('data/out/hexes.geojson'))
P = {f['properties']['h3']: f['properties'] for f in d['features']}
def at(lat, lon): return P[h3.latlng_to_cell(lat, lon, 9)]
up = at(43.1740, 76.9170)['pm25_winter']      # Ерменсай (верх)
low = at(43.2840, 76.9400)['pm25_winter']     # у вокзала Алматы-1 / север
print("pm25_winter Ermensay", up, "north", low)
assert up is not None and low is not None and up < low
PY
grep -q 'зимы 2017–2020' data/out/factors.json && grep -q 'm.period' web/index.html && echo "period label present"
echo "s3 CHECK PASSED"
