"""s1-r03: join grid + every layer, add percentiles (1 = better), write data/out/hexes.geojson + factors.json"""
import json
import h3, pandas as pd
from .common import OUT, LAYERS, log
from .factors import FACTORS

def main():
    df = pd.read_parquet(OUT / "grid.parquet")
    for f in sorted(LAYERS.glob("*.parquet")):
        layer = pd.read_parquet(f)
        cols = [c for c in layer.columns if c != "h3"]
        df = df.merge(layer, on="h3", how="left")
        log(f"layer {f.name}: {cols}, coverage {layer.h3.isin(df.h3).mean():.0%}")
    present = []
    for name, meta in FACTORS.items():
        if name not in df.columns:
            continue
        present.append(name)
        s = df[name].astype(float)
        pct = s.rank(pct=True, method="average")
        df[name + "_p"] = (1 - pct if meta["better"] == "low" else pct).round(4)
        df.loc[s.isna(), name + "_p"] = None
    feats = []
    for r in df.to_dict("records"):
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(r["h3"])]
        ring.append(ring[0])
        props = {k: (None if pd.isna(v) else v) for k, v in r.items() if k not in ("lat", "lon")}
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props})
    (OUT / "hexes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "factors.json").write_text(json.dumps({k: FACTORS[k] for k in present}, ensure_ascii=False, indent=1))
    log(f"hexes.geojson: {len(feats)} features, factors {present}, {round((OUT/'hexes.geojson').stat().st_size/1e6,1)} MB")

if __name__ == "__main__":
    main()
