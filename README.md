# almaty-livemap

Карта «где в Алматы удобно жить» на гексах H3 res 9 с ползунками весов. Продукт — `docs/prd.md`, проверенные источники — `docs/research/sources.md`, состояние работы — `.claude/STATE.md`.

```bash
uv sync
uv run python -m pipeline.grid        # граница города → 5582 гекса
uv run python -m pipeline.metro       # минуты пешком до метро (OSM)
uv run python -m pipeline.pop         # население Kontur (res 8)
uv run python -m pipeline.crime fetch && uv run python -m pipeline.crime agg   # gis.kgp.kz, 2023–2025
uv run python -m pipeline.air sensors && uv run python -m pipeline.air history && uv run python -m pipeline.air grid
uv run python -m pipeline.transit     # маршруты ОТ в 400 м (OSM)
uv run python -m pipeline.poi fetch && uv run python -m pipeline.poi grid      # инфраструктура в 1 км (OSM)
uv run python -m pipeline.district    # районы + цены из config/prices.yaml
uv run python -m pipeline.build       # → data/out/hexes.geojson + factors.json
python3 -m http.server 8080           # → http://localhost:8080/web/
```

Доезд на авто и ОТ в 8:30 (2GIS) — `pipeline/reach.py`, нужен `TWOGIS_KEY` в окружении и `config/destinations.yaml`; `uv run python -m pipeline.reach plan` считает смету без запросов.

Проверки: `scripts/check-s1.sh … check-s6.sh` (headless-браузер silver).
