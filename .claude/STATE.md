# STATE — almaty-livemap

**Goal.** Личная карта Алматы на гексах H3 с ползунками весов факторов (docs/prd.md). Ledger: `.claude/slices.json` (6 слайсов). Spine: compound-v:get-shit-done.

**Next.** `export TWOGIS_KEY=…` в Terminal-табе → `uv run python -m pipeline.reach probe` (2 единицы) → `reach car` → `reach pt` → `bash scripts/check-s4.sh`. Потом публикация (пункт 5).

**Proof commands.** `bash scripts/check-s1.sh`, `check-s2.sh`, `check-s3.sh` → PASSED 2026-10-12. `check-s4.sh` → exit 2 BLOCKED (нет ключа). `check-s6.sh` → локальная часть.

**Done 2026-10-12.** Источники проверены (docs/research/sources.md). Слои: metro_min, crime_rate (84 624 точки + Kontur), pm25_winter (22 датчика), transit_proxy (OSM), district (8 районов). Страница: MapLibre, ползунки, попап, Топ-20. Код 2GIS написан, не запускался.

**Needs owner (руками).**
1. Ключ 2GIS нигде не виден (env, .env, .zshrc, история, Terminal-таб) — `export TWOGIS_KEY=…` в Terminal-табе или строка `TWOGIS_KEY=…` в `almaty-livemap/.env` (gitignored). Демо = 1000 единиц на API: `config/destinations.yaml` уже с одной точкой (центр) → 502 единицы на API. Свои точки — поменять там же; 2 точки уже не влезают в демо.
2. `uv run python -m pipeline.reach probe` (2 единицы, проверяет формат) → `reach car` → `reach pt` → `bash scripts/check-s4.sh`.
3. Цены: сделано (`config/prices.yaml`, 2026-10-13, krisha по районам).
4. Публикация: репозиторий github.com/t1mdurden/almaty-livemap создан приватным и запушен; сделать публичным и включить Pages классификатор не дал — две команды в ledger s6-r03. После этого URL в README и открыть на телефоне (s6-r04).
6. По желанию: `launchctl load ops/com.almaty-livemap.airlog.plist` — часовой лог живых датчиков воздуха.

**Known limits.** Воздух — зимы 2017–2020 (архив), живых датчиков 4. Преступность на 1000 жителей взрывается у рынков (Алтын Орда). OSM-остановки есть лишь у ~54 % населённых гексов. Kontur насчитал 1,47 млн жителей на сетке.
