"""Shared paths, bbox, HTTP helpers. No secrets here; keys come from the environment."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "out"
LAYERS = OUT / "layers"
for p in (RAW, OUT, LAYERS):
    p.mkdir(parents=True, exist_ok=True)

# south, west, north, east — Almaty city + a margin
BBOX = (43.15, 76.75, 43.42, 77.15)
H3_RES = 9
UA = "almaty-livemap/0.1 (personal research; timamikhailov@gmail.com)"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

def log(*a):
    print(*a, file=sys.stderr, flush=True)

def overpass(query: str, cache: str | None = None, tries: int = 3) -> dict:
    """Run an Overpass query, rotating mirrors; cache the JSON under data/raw if asked."""
    if cache:
        f = RAW / cache
        if f.exists():
            return json.loads(f.read_text())
    last = None
    for attempt in range(tries):
        for url in OVERPASS_MIRRORS:
            try:
                r = requests.post(url, data={"data": query}, headers={"User-Agent": UA}, timeout=180)
                if r.status_code == 200 and r.text.lstrip().startswith("{"):
                    d = r.json()
                    if cache:
                        (RAW / cache).write_text(json.dumps(d, ensure_ascii=False))
                    return d
                last = f"{url} -> HTTP {r.status_code}: {r.text[:120]!r}"
            except requests.RequestException as e:
                last = f"{url} -> {e}"
            log("overpass retry:", last)
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Overpass failed on every mirror. Last: {last}")

def bbox_str() -> str:
    s, w, n, e = BBOX
    return f"{s},{w},{n},{e}"

def nominatim_polygon(q: str, cache: str) -> dict:
    """City polygon as GeoJSON geometry from Nominatim (cached)."""
    f = RAW / cache
    if f.exists():
        return json.loads(f.read_text())
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": q, "format": "jsonv2", "polygon_geojson": 1, "limit": 5},
        headers={"User-Agent": UA}, timeout=60,
    )
    r.raise_for_status()
    hits = [h for h in r.json() if h.get("osm_type") == "relation" and h.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")]
    if not hits:
        raise SystemExit(f"Nominatim returned no relation polygon for {q!r}")
    f.write_text(json.dumps(hits[0], ensure_ascii=False))
    return hits[0]
