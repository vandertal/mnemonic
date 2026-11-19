# Mnemonic backend

FastAPI app. See the repository root `CLAUDE.md` and `docs/` for the full picture.

```powershell
uv run fastapi dev src/mnemonic/main.py
uv run pytest
uv run ruff check . ; uv run ruff format .
```

Ingest the FastAPI docs into Postgres (needs `DATABASE_URL` in `.env`; safe to re-run):

```powershell
uv run python -m mnemonic.ingest
```
