# almaty-livemap

Карта «где в Алматы удобно жить» на гексах H3 с ползунками весов. Продукт описан в `docs/prd.md`, источники и их проверка — `docs/research/sources.md`, ход работы — `.claude/STATE.md`.

```bash
uv sync
uv run python -m pipeline.grid && uv run python -m pipeline.metro && uv run python -m pipeline.build
python3 -m http.server 8080   # then http://localhost:8080/web/ (port 8765 is taken by hired desk)
```
