# almaty-livemap — где в Алматы удобно жить

Карта: **https://t1mdurden.github.io/almaty-livemap/web/** (первая загрузка ~5 МБ данных).

Город разбит на ячейки H3 (res 9, ~0.1 км²), по каждой считаются факторы: пешком до метро, уличная преступность на 1000 жителей,
PM2.5 зимой и за последние 7 дней, время на авто и общественном транспорте до центра в 8:30 буднего дня, маршруты рядом,
магазины/школы/аптеки/парки в 1 км, ДТП рядом, цена м² по району, ЖК и объявлениям. Ползунки задают веса, балл — взвешенное
среднее перцентилей по жилым ячейкам города. Сверху — микрорайоны кружками и многоквартирные дома с зума 14, режим сравнения
двух точек, вкладка «О данных» с источниками и оговорками.

## Источники
OpenStreetMap (ODbL) · Комитет по правовой статистике и специальным учётам ГП РК, открытые слои ArcGIS gis.kgp.kz (преступления, ДТП) ·
Kontur Population 2023 (CC BY) · airkaz.org и AirGradient / Almaty Air Initiative (датчики PM2.5) · 2GIS Distance Matrix и Routing API
(время в пути, демо-ключ) · krisha.kz (цены по районам, ЖК и объявлениям; автоматический доступ — с разрешения Kolesa на разработку).
Подробности и измерения — `docs/research/sources.md`. Продукт — `docs/prd.md`. Состояние работы — `.claude/STATE.md`.

## Запуск пайплайна
```bash
uv sync
uv run python -m pipeline.grid && uv run python -m pipeline.metro && uv run python -m pipeline.pop
uv run python -m pipeline.crime fetch && uv run python -m pipeline.crime agg
uv run python -m pipeline.air sensors && uv run python -m pipeline.air history && uv run python -m pipeline.air grid
uv run python -m pipeline.air live && uv run python -m pipeline.air now        # живые датчики, раз в час (ops/*.plist)
uv run python -m pipeline.poi fetch && uv run python -m pipeline.poi grid
uv run python -m pipeline.transit && uv run python -m pipeline.dtp fetch && uv run python -m pipeline.dtp agg
uv run python -m pipeline.district && uv run python -m pipeline.mask
uv run python -m pipeline.reach plan   # 2GIS: нужен TWOGIS_KEY в окружении или .env; далее reach car | pt-dm | car-evening | grid
uv run python -m pipeline.build && uv run python -m pipeline.places && uv run python -m pipeline.buildings
python3 -m http.server 8080            # http://localhost:8080/web/
```
Ключи и сырые данные (`.env`, `data/raw/`) в репозиторий не попадают.

Проверки: `scripts/check-s1.sh … check-s6.sh` (headless-браузер silver).
