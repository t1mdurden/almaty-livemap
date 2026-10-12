# STATE — almaty-livemap

**Goal.** Личная карта Алматы на гексах H3 с ползунками весов факторов (docs/prd.md). Ledger: `.claude/slices.json` (6 слайсов). Spine: compound-v:get-shit-done.

**Next.** Публикацию он отложил («пока не делай github page»). Карта живёт локально: `python3 -m http.server 8791 --directory .` → http://localhost:8791/web/. Открытые строки: s6-r03 (Pages, отложено владельцем) и s6-r04 (его прогулка по карте).

**Proof commands.** `bash scripts/check-s1.sh`, `check-s2.sh`, `check-s3.sh` → PASSED 2026-10-12. `check-s4.sh` → exit 2 BLOCKED (нет ключа). `check-s6.sh` → локальная часть.

**Done 2026-10-12.** Источники проверены (docs/research/sources.md). Слои: metro_min, crime_rate (84 624 точки + Kontur), pm25_winter (22 датчика), transit_proxy (OSM), district (8 районов). Страница: MapLibre, ползунки, попап, Топ-20. Код 2GIS написан, не запускался.

**Needs owner (руками).**
1. Пройтись по карте на localhost:8791/web/, подвигать ползунки, открыть Топ-20 — его слово закрывает s6-r04.
2. Когда захочет ссылку: сделать репо публичным и включить Pages (команды в ledger s6-r03).
3. Свои точки в `config/destinations.yaml`: демо-бюджет 2GIS почти исчерпан (Distance Matrix ~944/1000, Routing ~82/1000 но 429) — вторая точка = пакет 6 700 ₽/мес или новый демо-ключ.

**Known limits.** Воздух — зимы 2017–2020 (архив), живых датчиков 4. Преступность на 1000 жителей взрывается у рынков (Алтын Орда). OSM-остановки есть лишь у ~54 % населённых гексов. Kontur насчитал 1,47 млн жителей на сетке.
