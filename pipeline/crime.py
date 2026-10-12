"""s2: crime points from the Committee on Legal Statistics ArcGIS server -> per-hex counts and rates.

Usage: python -m pipeline.crime fetch | agg | count
Source: https://gis.kgp.kz/arcgis/rest/services/KPSSU/crime/FeatureServer/1 (public, read-only).
"""
import sys, json, time
import h3, pandas as pd, requests
from .common import RAW, OUT, LAYERS, BBOX, UA, log

LAYER = "https://gis.kgp.kz/arcgis/rest/services/KPSSU/crime/FeatureServer/1/query"
YEARS = (2023, 2024, 2025)           # last three full years; 2026 is partial
PAGE = 5000                          # server maxRecordCount
MIN_POP = 100                        # res-8 cells with fewer residents get no rate (too noisy)
FIELDS = "objectid,yr,period,crime_code,hard_code,stat,dat_sover,organ,reg_code,city_code,fe1r29p1_id,weekday,discontinued"
# Street-crime articles of the Criminal Code of Kazakhstan (what a resident meets outside):
# 188 кража, 191 грабёж, 192 разбой, 293 хулиганство, 106/107 вред здоровью, 99 убийство, 194 вымогательство
STREET_PREFIXES = ("ст.188", "ст.191", "ст.192", "ст.293", "ст.106", "ст.107", "ст.99", "ст.194")
# Excluded from the street index on purpose: ст.190 мошенничество (mostly online, geocoded to the victim), ст.189 присвоение.

def base_params(where):
    s, w, n, e = BBOX
    return {"where": where, "geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "f": "json"}

def server_count(where) -> int:
    r = requests.get(LAYER, params={**base_params(where), "returnCountOnly": "true"}, headers={"User-Agent": UA}, timeout=120, verify=True)
    r.raise_for_status()
    return r.json()["count"]

def fetch_year(yr) -> pd.DataFrame:
    where = f"yr={yr}"
    cache = RAW / f"crime_{yr}.parquet"
    expected = server_count(where)
    if cache.exists():
        df = pd.read_parquet(cache).drop_duplicates("objectid")
        if len(df) == expected:
            log(f"{yr}: cached {len(df)} == server {expected}")
            return df
        log(f"{yr}: cache {len(df)} != server {expected}, refetching")
    rows, offset = [], 0
    while True:
        p = {**base_params(where), "outFields": FIELDS, "outSR": 4326, "orderByFields": "objectid",
             "resultOffset": offset, "resultRecordCount": PAGE}
        for attempt in range(4):
            try:
                r = requests.get(LAYER, params=p, headers={"User-Agent": UA}, timeout=180)
                d = r.json()
                if "error" in d:
                    raise RuntimeError(d["error"])
                break
            except Exception as e:
                log(f"{yr} offset {offset}: {e}; retry {attempt+1}")
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"gave up at {yr} offset {offset}")
        feats = d.get("features", [])
        for f in feats:
            a = f["attributes"]; g = f.get("geometry") or {}
            a["lon"], a["lat"] = g.get("x"), g.get("y")
            rows.append(a)
        log(f"{yr}: +{len(feats)} (total {len(rows)}/{expected})")
        if len(feats) < PAGE and not d.get("exceededTransferLimit"):
            break
        offset += len(feats)
        time.sleep(0.5)
    df = pd.DataFrame(rows).drop_duplicates("objectid")   # paging overlaps a little; objectid is the truth
    if len(df) != expected:
        log(f"WARNING {yr}: fetched {len(df)} vs server {expected}")
    df.to_parquet(cache, index=False)
    return df

def fetch():
    df = pd.concat([fetch_year(y) for y in YEARS], ignore_index=True).drop_duplicates("objectid")
    df = df.dropna(subset=["lat", "lon"])
    df.to_parquet(RAW / "crime.parquet", index=False)
    log(f"crime.parquet: {len(df)} points, years {sorted(df.yr.unique())}")

def count():
    total = 0
    for y in YEARS:
        n = server_count(f"yr={y}"); total += n; print(f"server yr={y}: {n}")
    local = len(pd.read_parquet(RAW / "crime.parquet")) if (RAW / "crime.parquet").exists() else 0
    print(f"server total {total} | local {local}")
    return total == local

def agg():
    df = pd.read_parquet(RAW / "crime.parquet")
    grid = pd.read_parquet(OUT / "grid.parquet")
    df["h3"] = [h3.latlng_to_cell(la, lo, 9) for la, lo in zip(df.lat, df.lon)]
    df["grave"] = df.hard_code.astype(str).isin(["3", "4"])
    df["street"] = df.stat.fillna("").str.startswith(STREET_PREFIXES)
    g = df.groupby("h3").agg(crime_n=("objectid", "size"), crime_grave_n=("grave", "sum"), crime_street_n=("street", "sum"))
    g = g.reindex(grid.h3, fill_value=0)
    # ring smoothing: own cell + 0.5 × mean of the 6 neighbours
    idx = g.to_dict("index")
    out = []
    for c in grid.h3:
        nb = [n for n in h3.grid_ring(c, 1) if n in idx]
        row = {"h3": c}
        for col in ("crime_n", "crime_grave_n", "crime_street_n"):
            own = idx[c][col]
            ring = sum(idx[n][col] for n in nb) / len(nb) if nb else 0
            row[col + "_s"] = round(own + 0.5 * ring, 2)
            row[col] = int(own)
        out.append(row)
    res = pd.DataFrame(out)
    res["crime_street_yr"] = (res["crime_street_n_s"] / len(YEARS)).round(2)   # per year, smoothed
    # rate: street crimes per year per 1000 residents, at the res-8 parent (Kontur population lives there)
    pop = pd.read_parquet(LAYERS / "pop.parquet")[["h3", "h3_r8", "pop_r8"]]
    res = res.merge(pop, on="h3", how="left")
    per8 = res.groupby("h3_r8")["crime_street_n"].sum()
    res["crime_street_r8"] = res.h3_r8.map(per8)
    res["crime_rate"] = (res.crime_street_r8 / len(YEARS) / res.pop_r8 * 1000).round(2)
    res.loc[res.pop_r8 < MIN_POP, "crime_rate"] = None
    res = res.drop(columns=["h3_r8", "pop_r8"])
    res.to_parquet(LAYERS / "crime.parquet", index=False)
    log(f"crime_rate: median {res.crime_rate.median()} p90 {res.crime_rate.quantile(.9)} null {res.crime_rate.isna().sum()} hexes (pop<{MIN_POP})")
    log(f"crime per hex: total {int(res.crime_n.sum())}, street {int(res.crime_street_n.sum())}, max/hex {int(res.crime_n.max())}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    {"fetch": fetch, "agg": agg, "count": lambda: sys.exit(0 if count() else 1)}[cmd]()
