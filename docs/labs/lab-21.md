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

**M2 — Ownership + resources.** [x]
Bearer on every data endpoint, `owner_id` / `X-API-Key` removed; migration 0003 (wipe legacy rows, `user_id` on sessions, FK owner → users); `/sessions` CRUD + pagination (`limit`/`offset`, `total`, `next`); `DELETE /auth/me`; JSON request logs (method, path, user, duration, status); `/health`; OpenAPI polish.
Check: Alice/Bob matrix — Bob gets 404 on Alice's session, document, chunk, flashcards; no token → 401.

**M3 — SPA + deploy.** [ ] — SPA code part done (login/register, Bearer client, server sessions, smoke); deploy part still open
Login/register pages, token in `api/client.ts`, 401 → login, access-code gate removed, sessions list from the server, i18n uk/en, smoke script updated. Then: merge `lab-21` → `main`, set `JWT_SECRET` (+ optional `REGISTRATION_CODE`) on Render, start command runs `alembic upgrade head`.
Check: register + chat + upload on the live URL; second account sees nothing of the first.

**M4 — Tests, CI/CD, close.** [ ] — code part done (integration tests, vitest, CI, render.yaml CD, README, secrets audit, Reflection drafts); pending: vitest install, first CI run, deploy, Reflection rewrite, tag
Integration tests against real Postgres+pgvector (db/ingest/store), SSE-parser unit tests (vitest), GitHub Actions (backend + frontend), deploy only after CI passes, README (live URL, curl, ER diagram, status codes, limitations), Reflection, tag `lab-21`.
Check: CI green on `main`; a red test blocks the deploy.

## Reflection

> **Draft: developer must rewrite in own words.** Written from the real code; check every claim (run it, open the
> file) before the defense.

**1. `curl` the live API: register, log in, fetch a protected resource.**
Use the bash or PowerShell block in the root `README.md` ("Try the API with curl"). Show: `POST /auth/register` → 201
with `{id, email, created_at}` (no hash in the response, `UserOut` has no such field); `POST /auth/login` is an
OAuth2 **form** (`username` = email) → `{access_token, token_type, expires_in}`; `GET /sessions` without the header
→ 401 with `WWW-Authenticate: Bearer`; with `Authorization: Bearer $TOKEN` → 200 and a page `{items, total, ...}`.
Free Render plan: wake the service up a minute before (`/health`).

**2. One request end to end (`POST /sessions`).**
`curl` → Render → uvicorn → FastAPI middlewares (`log_requests` in `main.py` outermost, then CORS) → route
`create_session` in `routes_sessions.py`. Its dependencies run first: `get_current_user` (`auth.py`) reads the
Bearer header, `decode_token` checks the HS256 signature and `exp`, then `store.get_user(sub)` loads the user (a
deleted account fails here) → Pydantic validates the body (`SessionCreate`, title stripped, length limits) →
`asyncio.to_thread(store.create_session, user.id, title)` (psycopg is blocking, the event loop must not wait) →
`PgStore.create_session` runs `INSERT INTO sessions (id, user_id, title) VALUES (gen_random_uuid(), %s, %s) RETURNING
...` in one transaction on Neon → the row becomes `SessionOut` JSON, status 201. Last, `log_requests` writes one
JSON line: method, route template, status, duration, user id.

**3. The password in the database.**
`SELECT email, password_hash FROM users` shows `$argon2id$v=19$m=...,t=...,p=...$<salt>$<hash>`. `hash_password`
in `auth.py` uses pwdlib's `PasswordHash.recommended()` = argon2id. The string carries the algorithm, its cost
parameters and a random salt, so equal passwords give different hashes and `verify_password` can recompute.
Argon2id is slow and **memory-hard** on purpose: SHA-256 can be tried billions of times per second on a GPU, argon2
makes each guess cost time and RAM. (The brief asks about bcrypt: same idea, a slow salted hash with a cost factor;
argon2id adds the memory cost and is the current OWASP first choice.) Hashing runs in `asyncio.to_thread` because it
is CPU-bound. The integration test `test_http_register_login_session_upload_and_a_stranger_gets_404` checks the
stored value starts with `$argon2id$`.

**4. The JWT structure.**
Three base64url parts joined by dots: **header** `{"alg": "HS256", "typ": "JWT"}`, **payload** `{"sub": "<user
uuid>", "iat": ..., "exp": ...}` (`create_access_token`), **signature** = HMAC-SHA256(header.payload, `JWT_SECRET`).
Header and payload are only encoded, not encrypted: anyone can read them on jwt.io, so nothing secret goes there. The
signature makes them tamper-proof: change `sub` and the signature no longer matches. `decode_token` passes
`algorithms=["HS256"]` explicitly (never trust the token's own `alg`, e.g. `none`) and requires `exp` and `sub`.

**5. Authentication vs authorization.**
Authentication = *who are you*: login checks the password, later requests prove identity with the token
(`get_current_user`). Authorization = *what may you touch*: every query has `AND user_id = %s` / `AND owner_id = %s`
in `store.py`, so Bob gets 404 for Alice's session (`test_ownership.py`, and the integration tests on real
Postgres). Failing authentication → 401; failing authorization here → 404 (403 would confirm the id exists), and 403
only for a wrong registration code.

**6. What goes wrong if...**
- *the JWT secret leaks*: anyone can sign a token with any `sub` and act as any user, for as long as the secret is
  valid. There is no revocation list. Fix: rotate `JWT_SECRET` on Render: every existing token becomes invalid, all
  users log in again. That is why it is only an env var, never in the repo (history audited in M4).
- *two users register the same email at the same time*: `PgStore.create_user` does not "check, then insert"; the
  UNIQUE constraint on `users.email` decides, one INSERT wins and the other gets `UniqueViolation` → `EmailTaken` →
  409. Proven by `test_two_parallel_registrations_of_one_email_exactly_one_wins` (two threads, a barrier, real
  Postgres). The same idea for uploads: `pg_advisory_xact_lock` in `add_document`, tested by
  `test_parallel_uploads_cannot_pass_the_limit`.
- *the database is unreachable for 30 s*: every `psycopg.connect` fails with `OperationalError`, so data requests
  answer 500 (there is no retry and no pool yet). `/health` still answers 200 (liveness only), so Render does not
  restart anything; since we open a connection per call, the app recovers by itself when Neon is back. A deploy in
  that window fails at `alembic upgrade head` and Render keeps the previous version. Improvement: catch
  `OperationalError` → 503 + `Retry-After`, add a connection pool with a timeout.

**7. SQL injection.**
Building SQL by gluing user input into the string, e.g. `f"... WHERE email = '{email}'"` with
`email = "x' OR '1'='1"`. We never do that: every query in `store.py` and `ingest/db.py` uses psycopg placeholders
(`%s`) and passes values separately (`conn.execute(sql, (email,))`), so the server receives the value as data, never
as SQL. The only f-string SQL is in the test fixture (`TRUNCATE {TABLES}`) and uses a constant. The ORM-free choice
(ADR 0004) makes this our responsibility, not the library's.

**8. The hardest bug.** *(developer: pick your own; candidates from the history)*
- The SSE parser bug found in M4: when `\r` and `\n` of one CRLF arrived in two network chunks, normalising each
  chunk turned them into two line breaks = a false end of event (`sse.ts`, test "does not end an event early").
- The document-limit race (without a lock, two parallel uploads could both count 4 < 5 and both insert); prevented by
  `pg_advisory_xact_lock(hashtext(owner_id))` inside the same transaction.
- Deploy side: the destructive migration 0003 had to run on the Neon `dev` branch first.
