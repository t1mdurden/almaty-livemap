# STATE — almaty-livemap

**Goal.** Личная карта Алматы на гексах H3 с ползунками весов факторов (docs/prd.md). Ledger: `.claude/slices.json` (6 слайсов, 30 строк). Spine: compound-v:get-shit-done.

**Next.** s2-r01 — `pipeline/crime.py fetch`: 84 624 точек 2023–2025 из gis.kgp.kz постранично в data/raw/crime.parquet.

**Proof command.** `bash scripts/check-s1.sh` → s1 CHECK PASSED (2026-10-12).

**Done.** 2026-10-12: исследование источников (docs/research/sources.md), ledger, uv-окружение (python 3.12, h3 4.5, geopandas 1.2).

**Needs owner.** 2GIS ключ в `TWOGIS_KEY`; `config/destinations.yaml`; решение о пакете 6 700 ₽; `config/prices.yaml`; GitHub-репозиторий для Pages.
