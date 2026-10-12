#!/usr/bin/env bash
# s1 check: pipeline builds ≥3000 hexes with metro_min; the page renders them and a slider changes a hex colour.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m pipeline.grid && uv run python -m pipeline.metro && uv run python -m pipeline.build
uv run python - <<'PY'
import json, h3
d = json.load(open('data/out/hexes.geojson'))
n = len(d['features']); assert n >= 3000, n
props = {f['properties']['h3']: f['properties'] for f in d['features']}
assert all('metro_min' in p for p in props.values())
abai = h3.latlng_to_cell(43.2392, 76.9468, 9)      # ст. метро Абай
erm  = h3.latlng_to_cell(43.1740, 76.9170, 9)      # Ерменсай
a, e = props[abai]['metro_min'], props[erm]['metro_min']
print(f"hexes={n} metro_min Abai={a} Ermensay={e}")
assert a < 5 and e > 60, (a, e)
json.dump({"abai": h3.cell_to_latlng(abai)}, open('data/out/.check-points.json','w'))
PY
PORT=8791
python3 -m http.server $PORT --bind 127.0.0.1 >/dev/null 2>&1 & SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
sleep 1
S="silver --session s1check --enable-actions"
ev(){ $S eval "$1" --json | jq -r '.data' | grep -v '⟦' | tr -d '\n'; }
$S open "http://localhost:$PORT/web/" >/dev/null
for i in $(seq 1 40); do
  r=$(ev "!!(window.__app && __app.ready && __app.idle)")
  if [ "$r" = "true" ]; then break; fi
  sleep 1
done
[ "$r" = "true" ] || { echo "page never became ready: $($S console --level error)"; exit 1; }
read -r LAT LON < <(jq -r '.abai | "\(.[0]) \(.[1])"' data/out/.check-points.json)
C1=$(ev "JSON.stringify(__app.pixelAt($LON,$LAT))")
$S eval "__app.setWeight('metro_min', 0)" >/dev/null
for i in $(seq 1 20); do
  r=$(ev "__app.idle")
  if [ "$r" = "true" ]; then break; fi
  sleep 0.5
done
C2=$(ev "JSON.stringify(__app.pixelAt($LON,$LAT))")
$S eval "__app.setWeight('metro_min', 1)" >/dev/null
echo "pixel at Abai with metro weight 1: $C1 ; with weight 0: $C2"
[ "$C1" != "$C2" ] || { echo "colour did not change"; exit 1; }
echo "s1 CHECK PASSED"
