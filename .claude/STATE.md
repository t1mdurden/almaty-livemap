# STATE — almaty-livemap

**Goal.** Личная карта Алматы на гексах H3 с ползунками весов факторов (docs/prd.md). Ledger: `.claude/slices.json` (6 слайсов, 30 строк). Spine: compound-v:get-shit-done.

**Next.** s1-r01 — `pipeline/grid.py`: граница Алматы из OSM → H3 res 9 → data/out/grid.parquet.

**Proof command.** `bash scripts/check-s1.sh` (пока не написан).

**Done.** 2026-10-12: исследование источников (docs/research/sources.md), ledger, uv-окружение (python 3.12, h3 4.5, geopandas 1.2).

**Needs owner.** 2GIS ключ в `TWOGIS_KEY`; `config/destinations.yaml`; решение о пакете 6 700 ₽; `config/prices.yaml`; GitHub-репозиторий для Pages.
