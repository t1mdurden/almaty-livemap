"""s3: winter PM2.5 per hex from airkaz.org sensors.

Usage: python -m pipeline.air sensors | history | grid | log
- sensors: sensor list (id, name, lat, lng) from the 2017–2020 workbook + the live page JSON
- history: daily means 2017-03 … 2020-09 from xls/daily_almaty_6oct20.xlsx -> winter (Nov–Feb) mean per sensor
- grid:    IDW interpolation of the winter mean onto the hex grid -> layers/air.parquet (pm25_winter)
- log:     append the current hourly values of live sensors to data/raw/air_log.parquet (idempotent)
"""
import sys, re, json, math, datetime as dt
import h3, pandas as pd, requests, openpyxl
from .common import RAW, OUT, LAYERS, UA, log

XLSX_URL = "https://airkaz.org/xls/daily_almaty_6oct20.xlsx"
PAGE_URL = "https://airkaz.org/almaty.php"
DIR = RAW / "airkaz"; DIR.mkdir(exist_ok=True)
XLSX = DIR / "daily_almaty_6oct20.xlsx"
WINTER = (11, 12, 1, 2)
MIN_DAYS = 60
IDW_P, IDW_K, IDW_RADIUS_M = 2, 5, 4000

def _get(url, **kw):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=120, verify=False, **kw)
    r.raise_for_status()
    return r

def page_json():
    s = _get(PAGE_URL).text
    best = None
    for m in re.finditer(r'\[\{"id"', s):
        start, depth = m.start(), 0
        for j in range(start, len(s)):
            if s[j] == "[": depth += 1
            elif s[j] == "]":
                depth -= 1
                if depth == 0: break
        chunk = s[start:j + 1]
        if "pm25" in chunk and (best is None or len(chunk) > len(best)): best = chunk
    return json.loads(best)

def sensors():
    if not XLSX.exists():
        XLSX.write_bytes(_get(XLSX_URL).content)
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    rows = [r for r in wb["sensors"].iter_rows(values_only=True) if r[0] is not None and r[0] != "id"]
    hist = pd.DataFrame(rows, columns=["id", "name", "city", "lat", "lng"]).dropna(subset=["lat"])
    hist["id"] = hist["id"].astype(int)
    live = pd.DataFrame(page_json())
    live = live[live.city.astype(str).str.startswith("Алматы")][["id", "name", "lat", "lng"]].drop_duplicates("id")
    live["id"] = live["id"].astype(int); live["lat"] = live.lat.astype(float); live["lng"] = live.lng.astype(float)
    allp = pd.concat([hist[["id", "name", "lat", "lng"]], live]).drop_duplicates("id", keep="first")
    allp.to_parquet(RAW / "air_sensors.parquet", index=False)
    log(f"sensors: {len(hist)} in workbook, {len(live)} on live page, {len(allp)} distinct")

def history():
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    ws = wb["data"]
    it = ws.iter_rows(values_only=True)
    header = next(it)
    cols = [(i + 1, int(c)) for i, c in enumerate(header[1:]) if isinstance(c, (int, float))]   # skip 'Grand Total'
    ids = [sid for _, sid in cols]
    recs, year, prev = [], 2017, None
    for r in it:
        if r[0] is None: continue
        try:
            d = dt.datetime.strptime(f"{r[0]}-{year}", "%d-%b-%Y").date()
        except ValueError:
            continue
        if prev and d < prev:            # day-month label wrapped into the next year
            year += 1; d = d.replace(year=year)
        prev = d
        for (ci, sid) in cols:
            v = r[ci] if ci < len(r) else None
            if isinstance(v, (int, float)):
                recs.append({"date": d, "id": sid, "pm25": float(v)})
    df = pd.DataFrame(recs)
    df.to_parquet(DIR / "daily.parquet", index=False)
    w = df[pd.to_datetime(df.date).dt.month.isin(WINTER)]
    agg = w.groupby("id").agg(pm25_winter=("pm25", "mean"), days=("pm25", "size")).reset_index()
    agg = agg[agg.days >= MIN_DAYS]
    agg.to_parquet(RAW / "air_winter.parquet", index=False)
    log(f"history: {len(df)} sensor-days {df.date.min()}…{df.date.max()}; winter means for {len(agg)} sensors (≥{MIN_DAYS} days): median {agg.pm25_winter.median():.1f} µg/m³")

def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))

def grid():
    sens = pd.read_parquet(RAW / "air_sensors.parquet").merge(pd.read_parquet(RAW / "air_winter.parquet"), on="id")
    g = pd.read_parquet(OUT / "grid.parquet")
    pts = list(zip(sens.lat, sens.lng, sens.pm25_winter))
    out = []
    for r in g.itertuples():
        ds = sorted(((_hav(r.lat, r.lon, la, lo), v) for la, lo, v in pts))[:IDW_K]
        ds = [(d, v) for d, v in ds if d <= IDW_RADIUS_M]
        if not ds:
            out.append({"h3": r.h3, "pm25_winter": None}); continue
        if ds[0][0] < 1: val = ds[0][1]
        else:
            w = [1 / d ** IDW_P for d, _ in ds]; val = sum(wi * v for wi, (_, v) in zip(w, ds)) / sum(w)
        out.append({"h3": r.h3, "pm25_winter": round(val, 1)})
    df = pd.DataFrame(out)
    df.to_parquet(LAYERS / "air.parquet", index=False)
    log(f"pm25_winter: {len(sens)} sensors used; coverage {df.pm25_winter.notna().mean():.0%}; min {df.pm25_winter.min()} max {df.pm25_winter.max()}")

def log_now():
    live = pd.DataFrame(page_json())
    fresh = pd.to_datetime(live.date, errors="coerce") >= pd.Timestamp.now() - pd.Timedelta(days=2)
    live = live[(live.city.astype(str).str.startswith("Алматы")) & (live.hour == "now") & fresh]
    live = live[["id", "date", "pm25", "pm10"]].copy()
    live["id"] = live.id.astype(int); live["ts"] = pd.to_datetime(live.date).dt.floor("h")
    live = live.drop(columns=["date"]).drop_duplicates(["id", "ts"])
    f = RAW / "air_log.parquet"
    old = pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=live.columns)
    new = pd.concat([old, live]).drop_duplicates(["id", "ts"])
    new.to_parquet(f, index=False)
    log(f"air log: +{len(new) - len(old)} rows, {len(new)} total, {live.id.nunique()} live sensors")

if __name__ == "__main__":
    import urllib3; urllib3.disable_warnings()
    {"sensors": sensors, "history": history, "grid": grid, "log": log_now}[sys.argv[1] if len(sys.argv) > 1 else "sensors"]()
