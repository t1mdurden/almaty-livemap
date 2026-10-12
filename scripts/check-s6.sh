#!/usr/bin/env bash
# s6 check (local part): Top-20 renders 20 rows and changes with weights; districts assigned; prices present if filled.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run python -m pipeline.district && uv run python -m pipeline.build
PORT=8791; python3 -m http.server $PORT --bind 127.0.0.1 >/dev/null 2>&1 & SRV=$!; trap 'kill $SRV 2>/dev/null || true' EXIT; sleep 1
S="silver --session s6check --enable-actions"
ev(){ $S eval "$1" --json | jq -r '.data' | grep -v '⟦' | tr -d '\n'; }
$S open "http://localhost:$PORT/web/" >/dev/null
for i in $(seq 1 40); do r=$(ev "!!(window.__app && __app.ready && __app.idle)"); if [ "$r" = "true" ]; then break; fi; sleep 1; done
[ "$r" = "true" ] || { echo "page not ready"; exit 1; }
N=$(ev "document.querySelectorAll('#top li').length"); [ "$N" = "20" ] || { echo "top list has $N rows"; exit 1; }
T1=$(ev "__app.top[0]"); $S eval "Object.keys(__app.weights).slice(1).forEach(k=>__app.setWeight(k,0))" >/dev/null; sleep 1; T2=$(ev "__app.top[0]")
$S eval "Object.keys(__app.weights).forEach(k=>__app.setWeight(k,1))" >/dev/null
echo "top-1 all weights: $T1 ; metro only: $T2"; [ "$T1" != "$T2" ] || { echo "top list did not change"; exit 1; }
D=$(ev "Object.values(__app.hexes).filter(p=>p.district).length"); echo "hexes with district: $D"; [ "$D" -gt 5000 ]
PRICED=$(ev "Object.values(__app.hexes).filter(p=>p.price_m2).length"); echo "hexes with price: $PRICED"
echo "s6 LOCAL CHECK PASSED (Pages URL + owner's phone walk remain)"
