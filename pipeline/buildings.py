"""Apartment buildings (OSM building=apartments) carrying their hex's factor percentiles -> data/out/buildings.geojson.
Drawn on the page from zoom 14 so the owner can see which houses sit in a good hex."""
import json
import h3
from .common import RAW, OUT, log

KEEP = ("h3", "district", "price_m2")

def main():
    hexes = {f["properties"]["h3"]: f["properties"] for f in json.load(open(OUT / "hexes.geojson"))["features"]}
    d = json.loads((RAW / "apartments.json").read_text())
    feats, skipped = [], 0
    for e in d["elements"]:
        g = e.get("geometry")
        if not g or len(g) < 4: continue
        lat = sum(p["lat"] for p in g) / len(g); lon = sum(p["lon"] for p in g) / len(g)
        c = h3.latlng_to_cell(lat, lon, 9)
        if c not in hexes: skipped += 1; continue
        t = e.get("tags", {})
        props = {"osm": e["id"], "name": t.get("name"), "street": t.get("addr:street"), "house": t.get("addr:housenumber"),
                 "levels": t.get("building:levels"), "year": t.get("start_date") or t.get("year_of_construction"), "h3": c}
        for k, v in hexes[c].items():
            if k.endswith("_p"): props[k] = v
        ring = [[p["lon"], p["lat"]] for p in g]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props})
    (OUT / "buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    log(f"buildings: {len(feats)} apartment footprints kept, {skipped} outside built hexes; {round((OUT/'buildings.geojson').stat().st_size/1e6,1)} MB")

if __name__ == "__main__":
    main()
