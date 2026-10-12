"""Population per H3 res 8 hex from Kontur Population (CC BY, HDX) -> data/out/layers/pop.parquet (res 9, parent's value shared)

Source: https://data.humdata.org/dataset/kontur-population-kazakhstan (kontur_population_KZ_20231101.gpkg.gz, 15 MB)
"""
import gzip, shutil
import h3, pandas as pd, geopandas as gpd, requests
from .common import RAW, OUT, LAYERS, BBOX, UA, log

URL = "https://geodata-eu-central-1-kontur-public.s3.amazonaws.com/kontur_datasets/kontur_population_KZ_20231101.gpkg.gz"
DIR = RAW / "kontur"; DIR.mkdir(exist_ok=True)
GPKG = DIR / "kontur_population_KZ_20231101.gpkg"

def download():
    if GPKG.exists():
        return
    gz = GPKG.with_suffix(".gpkg.gz")
    with requests.get(URL, headers={"User-Agent": UA}, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(gz, "wb") as f:
            shutil.copyfileobj(r.raw, f)
    with gzip.open(gz, "rb") as src, open(GPKG, "wb") as dst:
        shutil.copyfileobj(src, dst)
    log(f"downloaded {GPKG.name}: {round(GPKG.stat().st_size/1e6,1)} MB")

def main():
    download()
    s, w, n, e = BBOX
    import pyogrio
    crs = pyogrio.read_info(GPKG)["crs"]
    box = gpd.GeoSeries.from_xy([w, e], [s, n], crs=4326).to_crs(crs).total_bounds
    g = gpd.read_file(GPKG, bbox=tuple(box)).to_crs(4326)
    log(f"kontur rows in bbox: {len(g)}, columns {list(g.columns)}, total pop {int(g.population.sum())}")
    pop8 = dict(zip(g["h3"], g["population"]))
    grid = pd.read_parquet(OUT / "grid.parquet")
    grid["h3_r8"] = [h3.cell_to_parent(c, 8) for c in grid.h3]
    grid["pop_r8"] = grid.h3_r8.map(pop8).fillna(0).astype(int)
    grid["pop"] = (grid.pop_r8 / 7).round(1)          # a res-8 cell has 7 res-9 children
    grid[["h3", "h3_r8", "pop_r8", "pop"]].to_parquet(LAYERS / "pop.parquet", index=False)
    log(f"pop: {int(grid['pop'].sum())} residents over {int((grid['pop']>0).sum())} populated hexes of {len(grid)}")

if __name__ == "__main__":
    main()
