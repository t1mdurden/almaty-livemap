# STATE — almaty-livemap

**Goal.** Личная карта Алматы на гексах H3 с ползунками весов факторов (docs/prd.md). Ledger: `.claude/slices.json` (6 слайсов). Spine: compound-v:get-shit-done.

**Next.** s5-r02/r03 — дождаться `pipeline.poi fetch` (Overpass медленный, кэш по категориям в data/raw/poi_*.json), затем `bash scripts/check-s5.sh`. Потом всё остальное ждёт владельца (см. ниже).

**Proof commands.** `bash scripts/check-s1.sh`, `check-s2.sh`, `check-s3.sh` → PASSED 2026-10-12. `check-s4.sh` → exit 2 BLOCKED (нет ключа). `check-s6.sh` → локальная часть.

**Done 2026-10-12.** Источники проверены (docs/research/sources.md). Слои: metro_min, crime_rate (84 624 точки + Kontur), pm25_winter (22 датчика), transit_proxy (OSM), district (8 районов). Страница: MapLibre, ползунки, попап, Топ-20. Код 2GIS написан, не запускался.

**Needs owner (руками).**
1. 2GIS: зарегистрироваться в Менеджере Платформы, создать демо-ключ → `export TWOGIS_KEY=…` (только окружение). Демо = 1000 единиц на API навсегда: хватает на 502 населённых гекса × 1 точку. 3 точки = 1506 → пакет 10 000 ед. за 6 700 ₽/мес.
2. `cp config/destinations.example.yaml config/destinations.yaml` и вписать свои точки.
3. `uv run python -m pipeline.reach plan` → если ОК: `reach car`, `reach pt`, `bash scripts/check-s4.sh`.
4. Вписать 8 цен м² в `config/prices.yaml` (krisha.kz/analytics) и дату.
5. Публикация: `gh repo create almaty-livemap --private --source . --push`, включить Pages (main, /root), URL в README; открыть на телефоне — это закрывает s6-r04.
6. По желанию: `launchctl load ops/com.almaty-livemap.airlog.plist` — часовой лог живых датчиков воздуха.

**Known limits.** Воздух — зимы 2017–2020 (архив), живых датчиков 4. Преступность на 1000 жителей взрывается у рынков (Алтын Орда). OSM-остановки есть лишь у ~54 % населённых гексов. Kontur насчитал 1,47 млн жителей на сетке.
