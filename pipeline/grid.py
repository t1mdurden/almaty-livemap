"""s1-r01: Almaty boundary (OSM via Nominatim) -> H3 res 9 cells -> data/out/grid.parquet"""
import h3, pandas as pd
from shapely.geometry import shape
from .common import OUT, H3_RES, nominatim_polygon, log

def main():
    hit = nominatim_polygon("Алматы, Казахстан", "almaty_nominatim.json")
    geom = shape(hit["geojson"])
    log("boundary:", hit.get("display_name"), "| osm relation", hit.get("osm_id"), "| area km²", round(geom.area * 111 * 111 * 0.72, 0))
    cells = h3.geo_to_cells(geom.__geo_interface__, H3_RES)
    n = len(cells)
    if not 3000 <= n <= 9000:
        raise SystemExit(f"unexpected cell count {n} — boundary or resolution is wrong")
    rows = [{"h3": c, "lat": h3.cell_to_latlng(c)[0], "lon": h3.cell_to_latlng(c)[1]} for c in cells]
    df = pd.DataFrame(rows).sort_values("h3").reset_index(drop=True)
    df.to_parquet(OUT / "grid.parquet", index=False)
    log(f"grid: {n} cells at res {H3_RES} -> {OUT/'grid.parquet'}")

if __name__ == "__main__":
    main()
