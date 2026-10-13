"""Road accidents (ДТП) 2023–2025 from the same ArcGIS server as crime -> per-hex counts within ~300 m (hex + ring 1) -> layers/dtp.parquet
Fact, not a weighted factor by default: dtp_300m (all), dtp_hurt_300m (with injured/killed if the field says so).
Layer: KPSSU/DTP/FeatureServer/0 — fields rta_date, yr, fd1r13p1 (injured count, assumed), fd1r13p2 (killed count, assumed), is_public_transport."""
import sys, time
import h3, pandas as pd, requests
from .common import RAW, OUT, LAYERS, BBOX, UA, log

LAYER = "https://gis.kgp.kz/arcgis/rest/services/KPSSU/DTP/FeatureServer/0/query"
YEARS = (2023, 2024, 2025)
PAGE = 2000
FIELDS = "objectid,yr,rta_date,fd1r13p1,fd1r13p2,is_public_transport,vehicle_category"

def base(where):
    s, w, n, e = BBOX
    return {"where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "f": "json"}

def fetch():
    rows = []
    for yr in YEARS:
        cache = RAW / f"dtp_{yr}.parquet"
        if cache.exists(): rows.append(pd.read_parquet(cache)); continue
        got, offset = [], 0
        while True:
            p = {**base(f"yr={yr}"), "outFields": FIELDS, "outSR": 4326, "orderByFields": "objectid", "resultOffset": offset, "resultRecordCount": PAGE}
            for attempt in range(5):
                try:
                    d = requests.get(LAYER, params=p, headers={"User-Agent": UA}, timeout=240).json()
                    if "error" in d: raise RuntimeError(d["error"])
                    break
                except Exception as ex:
                    log(f"dtp {yr} offset {offset}: {ex}; retry"); time.sleep(10 * (attempt + 1))
            else:
                raise SystemExit("dtp: gave up")
            feats = d.get("features", [])
            for f in feats:
                a = f["attributes"]; g = f.get("geometry") or {}; a["lon"], a["lat"] = g.get("x"), g.get("y"); got.append(a)
            log(f"dtp {yr}: {len(got)}")
            if len(feats) < PAGE and not d.get("exceededTransferLimit"): break
            offset += len(feats); time.sleep(0.5)
        df = pd.DataFrame(got).drop_duplicates("objectid"); df.to_parquet(cache, index=False); rows.append(df)
    df = pd.concat(rows, ignore_index=True).dropna(subset=["lat", "lon"])
    df.to_parquet(RAW / "dtp.parquet", index=False)
    log(f"dtp.parquet: {len(df)} accidents {YEARS}")

def agg():
    df = pd.read_parquet(RAW / "dtp.parquet")
    df["h3"] = [h3.latlng_to_cell(a, b, 9) for a, b in zip(df.lat, df.lon)]
    df["hurt"] = (pd.to_numeric(df.fd1r13p1, errors="coerce").fillna(0) + pd.to_numeric(df.fd1r13p2, errors="coerce").fillna(0)) > 0
    per = df.groupby("h3").agg(n=("objectid", "size"), hurt=("hurt", "sum")).to_dict("index")
    g = pd.read_parquet(OUT / "grid.parquet"); out = []
    for c in g.h3:
        n = hurt = 0
        for k in h3.grid_disk(c, 1):
            if k in per: n += per[k]["n"]; hurt += per[k]["hurt"]
        out.append({"h3": c, "dtp_300m": int(n), "dtp_hurt_300m": int(hurt)})
    o = pd.DataFrame(out); o.to_parquet(LAYERS / "dtp.parquet", index=False)
    log(f"dtp per hex (hex+ring): median {o.dtp_300m.median()}, p90 {o.dtp_300m.quantile(.9)}, max {o.dtp_300m.max()}")

if __name__ == "__main__":
    {"fetch": fetch, "agg": agg}[sys.argv[1] if len(sys.argv) > 1 else "fetch"]()
