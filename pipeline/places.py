"""Named places (микрорайоны / кварталы) from OSM place=neighbourhood|quarter|suburb.
Each built hex is assigned to the place polygon containing it, else to the nearest place point within 900 m.
-> data/out/places.geojson (point per place: name, n_hex, mean raw + mean percentile per factor)."""
import json, math
import h3, pandas as pd
from shapely.geometry import Point
from shapely.strtree import STRtree
from .common import RAW, OUT, LAYERS, log
from .factors import FACTORS
from .mask import _poly_from_element

NEAR_M = 900

def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))

def load_places():
    d = json.loads((RAW / "places.json").read_text())
    places = []
    for e in d["elements"]:
        t = e.get("tags", {}); name = t.get("name:ru") or t.get("name")
        if not name: continue
        poly = _poly_from_element(e) if e["type"] != "node" else None
        if e["type"] == "node":
            lat, lon = e["lat"], e["lon"]
        elif poly is not None and not poly.is_empty:
            c = poly.centroid; lat, lon = c.y, c.x
        elif "center" in e:
            lat, lon = e["center"]["lat"], e["center"]["lon"]
        else:
            continue
        places.append({"id": f"{e['type'][0]}{e['id']}", "name": name, "kind": t.get("place"), "lat": lat, "lon": lon, "poly": poly})
    # dedupe same name within 600 m (node + polygon of one микрорайон)
    out = []
    for p in sorted(places, key=lambda p: p["poly"] is None):   # polygons first
        if any(q["name"] == p["name"] and _hav(q["lat"], q["lon"], p["lat"], p["lon"]) < 600 for q in out): continue
        out.append(p)
    return out

def main():
    hexes = json.load(open(OUT / "hexes.geojson"))["features"]
    places = load_places()
    polys = [p["poly"] for p in places if p["poly"] is not None]
    poly_idx = [i for i, p in enumerate(places) if p["poly"] is not None]
    tree = STRtree(polys) if polys else None
    assign = {}
    for f in hexes:
        pr = f["properties"]
        ring = f["geometry"]["coordinates"][0]
        lat = sum(c[1] for c in ring) / len(ring); lon = sum(c[0] for c in ring) / len(ring)
        pt = Point(lon, lat); pid = None
        if tree is not None:
            hits = [j for j in tree.query(pt) if polys[j].contains(pt)]
            if hits: pid = poly_idx[hits[0]]
        if pid is None:
            dmin, best = NEAR_M, None
            for i, p in enumerate(places):
                dd = _hav(lat, lon, p["lat"], p["lon"])
                if dd < dmin: dmin, best = dd, i
            pid = best
        if pid is not None:
            assign.setdefault(pid, []).append(pr)
    feats = []
    for i, p in enumerate(places):
        rows = assign.get(i, [])
        if len(rows) < 2: continue
        props = {"id": p["id"], "name": p["name"], "kind": p["kind"], "n_hex": len(rows),
                 "district": max((r.get("district") for r in rows), key=lambda x: sum(1 for r in rows if r.get("district") == x)),
                 "price_m2": next((r.get("price_m2") for r in rows if r.get("price_m2")), None)}
        for k in FACTORS:
            vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
            pcts = [r[k + "_p"] for r in rows if isinstance(r.get(k + "_p"), (int, float))]
            props[k] = round(sum(vals) / len(vals), 1) if vals else None
            props[k + "_p"] = round(sum(pcts) / len(pcts), 3) if pcts else None
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]}, "properties": props})
    (OUT / "places.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    covered = sum(len(v) for v in assign.values())
    log(f"places: {len(places)} named, {len(feats)} with ≥2 hexes, hexes assigned {covered}/{len(hexes)}")

if __name__ == "__main__":
    main()
