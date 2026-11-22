# Lab 21 — REST API with Auth (Mnemonic)

Brief: `../Programming-Practice-Projects/labs/lab-21-rest-api-auth.md`.
Target: **Standard**. Advanced: pagination, structured JSON logging, automated tests, CI/CD (per-IP rate limiting already exists from lab 31).

## Key adaptation (defend this)

The brief builds a new API from "hello world". We already have a deployed API (lab 31) with **fake auth**:
`X-API-Key` (one shared secret) + `session_id` / `owner_id` UUIDs generated in the browser. Anyone who knows a UUID reads that space.
Lab 21 replaces it with **real accounts**: email + argon2 password hash → JWT → every data endpoint scopes rows to the user in the token.
Main resource for the Basic CRUD requirement: **chat sessions** (create / list / get / rename / delete). Documents already have list / upload / delete.

## Decisions (made upfront; recorded as ADR 0004 in M1)

| Topic | Decision | Why / trade-off |
|---|---|---|
| Migrations | Alembic, **raw SQL** in migrations, no ORM | `store.py` (psycopg) works and is tested; rewriting it to SQLAlchemy adds no product value. Brief allows SQL by hand. Cost: no autogenerate. |
| Baseline | Migration 0001 = exact current schema, all `IF NOT EXISTS` | Same file works on a fresh DB and on the live Neon DB (no-op there). Alembic becomes the only schema owner; app startup no longer creates tables. |
| Password hash | argon2id via `pwdlib`, run in a worker thread | passlib / python-jose are unmaintained; FastAPI docs use pwdlib + PyJWT. Hashing is CPU-heavy: must not block the event loop. |
| Token | JWT HS256 access token, 24 h, claims `sub`, `iat`, `exp`; decode with an explicit `algorithms=["HS256"]` | No refresh token (side quest if time). Logout = client forgets the token; **no server-side revocation** (stated limitation). |
| Login endpoint | OAuth2 password **form** (`username` = email) | Swagger "Authorize" button works for recruiters. SPA sends form-encoded. |
| Login errors | Unknown email and wrong password → the same 401; a dummy hash is verified when the user is missing | No user enumeration via message or timing. (Register still answers 409 on a taken email: accepted.) |
| Registration | Open, plus optional `REGISTRATION_CODE` env; stricter per-IP limit on `/auth/*` | Protects the free LLM budget and Neon storage. Empty code = open (lab 34 real users). |
| Token storage in SPA | localStorage | XSS-readable, same trade-off as lab 22. HttpOnly cookie rejected: SPA (Workers) and API (Render) are different origins → SameSite/CSRF complexity. |
| Legacy anonymous data | Deleted by migration 0003 | Demo uploads/chats with random owner UUIDs have no account to belong to. |
| Flashcard decks | Stay in localStorage, keyed by user id | Server-side decks = backlog. Limitation in README. |
| Dev database | Neon branch `dev` | M2 migration is destructive; production is touched only by the deliberate deploy step. |
| Git | Work on branch `lab-21`, merge to `main` after M3 | `main` deploys the backend; M2 breaks the old SPA until M3 lands. |

## Guide → ours → milestone

| Brief | Ours | M |
|---|---|---|
| Day 1 deploy first | already live (lab 31) | — |
| Day 3 DB + migrations from day one | Alembic baseline + `users` | M1 |
| Day 8 register + hash | `POST /auth/register`, argon2 | M1 |
| Day 9 login + JWT | `POST /auth/login`, `GET /auth/me` | M1 |
| Day 4 five CRUD endpoints | `/sessions` CRUD (+ documents) | M2 |
| Day 5–6 validation, status codes | Pydantic, 201/204/401/404/409/422/429 | M1–M2 |
| Day 7 OpenAPI polish | tags, descriptions, examples, Authorize | M2 |
| Day 10 protected routes, Alice/Bob | Bearer on all data endpoints, owner from token | M2 |
| Side quests | pagination + JSON request logs | M2 |
| Frontend (extension) | login/register pages, 401 → login, sessions from server | M3 |
| Day 11 deploy, secrets | `JWT_SECRET` on Render, `alembic upgrade head` on deploy | M3 |
| Tests, CI/CD | real-Postgres integration tests, SSE parser tests, GitHub Actions | M4 |
| Day 13 README, ER, curl | README, mermaid ER, curl examples, Reflection, tag | M4 |

## Milestones (4)

**M1 — Accounts (existing endpoints untouched).** [x]
Alembic baseline + `users`; `/auth/register|login|me`; argon2 in a thread; JWT; `JWT_SECRET` (required, ≥32 chars), `REGISTRATION_CODE`, auth rate limit; unit tests; ADR 0004. `X-API-Key` still works, so nothing live changes.
Check: `alembic upgrade head` on the dev DB (and down/up); Swagger **Authorize** works; wrong password 401; duplicate email 409; the DB row is an argon2 hash.

**M2 — Ownership + resources.** [ ]
Bearer on every data endpoint, `owner_id` / `X-API-Key` removed; migration 0003 (wipe legacy rows, `user_id` on sessions, FK owner → users); `/sessions` CRUD + pagination (`limit`/`offset`, `total`, `next`); `DELETE /auth/me`; JSON request logs (method, path, user, duration, status); `/health`; OpenAPI polish.
Check: Alice/Bob matrix — Bob gets 404 on Alice's session, document, chunk, flashcards; no token → 401.

**M3 — SPA + deploy.** [ ] — SPA code part done (login/register, Bearer client, server sessions, smoke); deploy part still open
Login/register pages, token in `api/client.ts`, 401 → login, access-code gate removed, sessions list from the server, i18n uk/en, smoke script updated. Then: merge `lab-21` → `main`, set `JWT_SECRET` (+ optional `REGISTRATION_CODE`) on Render, start command runs `alembic upgrade head`.
Check: register + chat + upload on the live URL; second account sees nothing of the first.

**M4 — Tests, CI/CD, close.** [ ]
Integration tests against real Postgres+pgvector (db/ingest/store), SSE-parser unit tests (vitest), GitHub Actions (backend + frontend), deploy only after CI passes, README (live URL, curl, ER diagram, status codes, limitations), Reflection, tag `lab-21`.
Check: CI green on `main`; a red test blocks the deploy.

## Reflection

Filled at M4 as drafts (developer rewrites in own words). Questions: live `curl` register → login → protected call; one request end to end; the hash in the DB (explain argon2); JWT structure on jwt.io; authentication vs authorization; what breaks if the secret leaks / two users register at once / the DB is down for 30 s; SQL injection (where we prevent it); hardest bug.
