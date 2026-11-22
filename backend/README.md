# Mnemonic backend

FastAPI app: accounts (argon2id + JWT), chat sessions, RAG over pgvector, documents, flashcards.
Project overview, architecture, ER diagram, curl examples and limitations: [../README.md](../README.md).

```powershell
Copy-Item .env.example .env       # fill in DATABASE_URL and JWT_SECRET
uv sync
uv run alembic upgrade head
uv run fastapi dev src/mnemonic/main.py   # http://127.0.0.1:8000/docs
uv run ruff check . ; uv run ruff format .
```

## Tests

```powershell
uv run pytest                     # unit tests (fakes, no database); integration tests are skipped
uv run pytest -m integration      # only the integration tests (needs TEST_DATABASE_URL, below)
```

Integration tests (`tests/integration/`) run against a **real Postgres + pgvector**: the real migrations, the real
`PgStore`, real constraints and locks. They run only when `TEST_DATABASE_URL` is set, and they **wipe that
database** (drop the `public` schema, then `alembic upgrade head`; tables are truncated between tests). They
refuse to start if `TEST_DATABASE_URL` points at the same server + database as `DATABASE_URL`.

```powershell
# a throwaway local database (Docker), or a separate Neon branch
docker run -d --name mnemonic-test -e POSTGRES_PASSWORD=test -p 5433:5432 pgvector/pgvector:pg17
$env:TEST_DATABASE_URL = "postgresql://postgres:test@localhost:5433/postgres"
uv run pytest
```

What they cover: migrations up → down → up; two parallel registrations of one email (exactly one wins);
sessions ownership and stable pagination; the document limit under parallel uploads (advisory lock); account
deletion cascades; chunk visibility (shared / own / foreign); idempotent ingest; pgvector search scoped to shared +
own; one HTTP flow (register → login → session → upload → a second user gets 404).

CI ([../.github/workflows/ci.yml](../.github/workflows/ci.yml)) runs all of them on every push / PR with a
`pgvector/pgvector:pg17` service container.

## Database schema (Alembic)

Alembic owns the schema; the app does not create tables at startup. Needs `DATABASE_URL` in `.env`.

```powershell
uv run alembic upgrade head     # create / update all tables (safe to re-run)
uv run alembic current          # which revision the database is on
uv run alembic downgrade -1     # undo the last migration
```

Migrations live in `migrations/versions/` and are plain SQL. New one: `uv run alembic revision -m "what changes"`.

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

## Auth

Set `JWT_SECRET` in `.env` (at least 32 chars; the app will not start without it):

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Try it in `/docs` (Authorize), or against a running server:
`uv run python scripts/auth_smoke.py http://127.0.0.1:8000`.
