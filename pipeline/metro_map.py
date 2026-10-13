"""Metro for the map: stations (OSM nodes) and the line geometry (OSM relation route=subway) -> data/out/metro.geojson"""
import json
import pandas as pd
from .common import RAW, OUT, log

def main():
    st = pd.read_parquet(RAW / "metro_stations.parquet")
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]}, "properties": {"kind": "station", "name": r.name}} for r in st.itertuples()]
    f = RAW / "metro_lines.json"
    n_lines = 0
    if f.exists():
        d = json.loads(f.read_text())
        for e in d["elements"]:
            if e["type"] != "relation" or e["tags"].get("route") != "subway": continue
            for m in e.get("members", []):
                if m["type"] == "way" and "geometry" in m and len(m["geometry"]) >= 2:
                    feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in m["geometry"]]},
                                  "properties": {"kind": "line", "name": e["tags"].get("name")}})
                    n_lines += 1
    (OUT / "metro.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    log(f"metro.geojson: {len(st)} stations, {n_lines} line segments")

if __name__ == "__main__":
    main()
