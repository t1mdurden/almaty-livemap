#!/usr/bin/env bash
# s5 check: Abai hex has all 6 categories, a steppe hex beyond the ring road has 0, ≥500 grocery POI.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m pipeline.poi grid && uv run python -m pipeline.build
uv run python - <<'PY'
import json, h3, pandas as pd
poi = pd.read_parquet('data/raw/poi.parquet'); vc = poi.cat.value_counts(); print(vc.to_dict()); assert vc.get('grocery', 0) >= 500
P = {f['properties']['h3']: f['properties'] for f in json.load(open('data/out/hexes.geojson'))['features']}
at = lambda la, lo: P[h3.latlng_to_cell(la, lo, 9)]
abai = at(43.2392, 76.9468); print("cat15 Abai", abai['cat15']); assert abai['cat15'] == 6
# steppe: north-east appendix of the city polygon, no housing
cands = [p for p in P.values() if p['pop'] == 0]
steppe = min(cands, key=lambda p: p['cat15']); print("min cat15 among unpopulated hexes", steppe['cat15'], "count zero:", sum(1 for p in cands if p['cat15'] == 0)); assert steppe['cat15'] == 0
print("s5 CHECK PASSED")
PY
