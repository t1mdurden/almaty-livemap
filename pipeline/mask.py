"""Built-up mask: a hex counts as 'built' when its centre lies in OSM residential/retail/commercial landuse,
or when it holds at least one apartment building. Mountains, steppe and the airport drop out of the map and
out of the percentiles. -> layers/mask.parquet (built: 0/1)"""
import json
import h3, pandas as pd
from shapely.geometry import shape, Polygon, MultiPolygon, Point
from shapely.ops import unary_union, polygonize, linemerge
from shapely.strtree import STRtree
from shapely.geometry import LineString
from .common import RAW, OUT, LAYERS, log

def _poly_from_element(e):
    if e["type"] == "way" and "geometry" in e:
        pts = [(p["lon"], p["lat"]) for p in e["geometry"]]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return None
    if e["type"] == "relation":
        lines = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in e.get("members", []) if m["type"] == "way" and m.get("role") in ("outer", "") and "geometry" in m]
        if not lines: return None
        polys = list(polygonize(linemerge(lines)))
        return unary_union(polys) if polys else None
    return None

def landuse_union():
    d = json.loads((RAW / "landuse_residential.json").read_text())
    polys = [p for p in (_poly_from_element(e) for e in d["elements"]) if p is not None and not p.is_empty]
    log(f"landuse polygons: {len(polys)}")
    return polys

def main():
    polys = landuse_union()
    tree = STRtree(polys)
    apts = json.loads((RAW / "apartments.json").read_text())
    apt_hex = set()
    for e in apts["elements"]:
        g = e.get("geometry")
        if not g: continue
        lat = sum(p["lat"] for p in g) / len(g); lon = sum(p["lon"] for p in g) / len(g)
        apt_hex.add(h3.latlng_to_cell(lat, lon, 9))
    # any residential-looking building (building=yes included, non-residential types excluded): a hex with ≥5 counts as built
    from .common import overpass, bbox_str
    from .houses import NONRES
    hd = overpass(f'[out:json][timeout:300][bbox:{bbox_str()}];(way["building"];);out center tags;', cache="all_buildings_center.json")
    house_n = {}
    for e in hd["elements"]:
        c = e.get("center"); t = e.get("tags", {})
        if not c or t.get("building") in NONRES or t.get("amenity") or t.get("shop") or t.get("office"): continue
        k = h3.latlng_to_cell(c["lat"], c["lon"], 9); house_n[k] = house_n.get(k, 0) + 1
    log(f"residential building centroids: {sum(house_n.values())}, hexes with ≥5: {sum(1 for v in house_n.values() if v >= 5)}")
    grid = pd.read_parquet(OUT / "grid.parquet")
    built = []
    for r in grid.itertuples():
        pt = Point(r.lon, r.lat)
        inside = any(polys[i].contains(pt) for i in tree.query(pt))
        built.append(int(inside or r.h3 in apt_hex or house_n.get(r.h3, 0) >= 5))
    grid["built"] = built
    grid[["h3", "built"]].to_parquet(LAYERS / "mask.parquet", index=False)
    log(f"built hexes: {sum(built)} of {len(grid)} ({sum(built)/len(grid):.0%}); apartment hexes {len(apt_hex)}")

if __name__ == "__main__":
    main()
