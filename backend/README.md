# Mnemonic backend

FastAPI app. See the repository root `CLAUDE.md` and `docs/` for the full picture.

```powershell
uv run fastapi dev src/mnemonic/main.py
uv run pytest
uv run ruff check . ; uv run ruff format .
```

## Database schema (Alembic)

Alembic owns the schema; the app does not create tables at startup. Needs `DATABASE_URL` in `.env`.

```powershell
uv run alembic upgrade head     # create / update all tables (safe to re-run)
uv run alembic current          # which revision the database is on
uv run alembic downgrade -1     # undo the last migration
```

Migrations live in `migrations/versions/` and are plain SQL. New one: `uv run alembic revision -m "what changes"`.

## Auth

Set `JWT_SECRET` in `.env` (at least 32 chars; the app will not start without it):

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Endpoints: `POST /auth/register`, `POST /auth/login` (form), `GET /auth/me`. Try them in `/docs` (Authorize),
or against a running server: `uv run python scripts/auth_smoke.py http://127.0.0.1:8000`.

## Ingest

Ingest the FastAPI docs into Postgres (needs the schema from `alembic upgrade head`; safe to re-run):

```powershell
uv run python -m mnemonic.ingest
```
