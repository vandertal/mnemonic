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

Try them in `/docs` (Authorize), or against a running server:
`uv run python scripts/auth_smoke.py http://127.0.0.1:8000`.

## Endpoints

Everything except `/auth/register`, `/auth/login`, `/health` and `/` needs `Authorization: Bearer <token>`
and only sees the rows of that account. Someone else's id answers **404**, like a missing one.

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register` | 201; 409 taken email; 403 wrong registration code |
| POST | `/auth/login` | OAuth2 form (`username` = email) -> token |
| GET / DELETE | `/auth/me` | who am I / delete my account and all its data (204) |
| POST / GET | `/sessions` | create (201) / list: `?limit=20&offset=0` -> `{items, total, limit, offset, next}` |
| GET / PATCH / DELETE | `/sessions/{id}` | read / rename `{title}` / delete (204) |
| GET | `/sessions/{id}/messages` | chat history |
| POST | `/chat` | `{session_id, message}` -> SSE stream |
| POST | `/flashcards` | `{session_id, message_id}` -> 3-5 cards |
| GET / POST | `/documents` | list / upload (.md, .txt, .pdf) |
| DELETE | `/documents/{id}` | 204 |
| GET | `/chunks/{id}` | text behind a citation |
| GET | `/health` | liveness, no auth, no database |

Every request is logged as one JSON line on the `mnemonic.access` logger (no headers, query strings or bodies).

Ownership smoke test (real server, real database, two accounts that clean up after themselves):
`uv run python scripts/ownership_smoke.py http://127.0.0.1:8000`.

## Ingest

Ingest the FastAPI docs into Postgres (needs the schema from `alembic upgrade head`; safe to re-run):

```powershell
uv run python -m mnemonic.ingest
```
