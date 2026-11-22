# Lab 21 — M1 task for Claude Code (autonomous): accounts

The developer PRE-APPROVED this plan. Do NOT wait for "ok": print a 5-line plan, then execute. Stop only if blocked by a missing secret or an irreversible decision.
Read first: CLAUDE.md, docs/labs/lab-21.md (decisions table!), then only the files you touch: backend/src/mnemonic/{main,store,security,config,schemas}.py, backend/tests/{conftest,fakes}.py, backend/src/mnemonic/ingest/{db,__main__}.py.
Rules: small Conventional commits, NO AI attribution lines, English code/docs/comments, PowerShell-compatible commands, `uv` only. Never print or log secrets, passwords, tokens or the DATABASE_URL.
`backend/.env` DATABASE_URL is the Neon **dev** branch (developer confirmed), not production.

## Scope
M1 only: Alembic + users + `/auth/*`. Existing endpoints keep working with `X-API-Key` and `owner_id`; do NOT touch their behaviour (that is M2).

## Tasks
0. `git branch --show-current`; if not `lab-21`: `git switch -c lab-21` (uncommitted docs come along). Commit the docs first: `docs: lab 21 plan`.
1. Approved dependencies: `uv add alembic pyjwt "pwdlib[argon2]"`. `email-validator` already comes with `fastapi[standard]` (verify; do not add another).
2. **Alembic** in `backend/` (`alembic.ini`, `migrations/`). `env.py` reads the URL from `get_settings().database_url` and rewrites `postgresql://` → `postgresql+psycopg://`; no URL or password in `alembic.ini`. No ORM metadata: migrations use `op.execute` with raw SQL.
   - `0001_baseline`: the exact current schema (`chunks_db.SCHEMA` + `store.SCHEMA`), all idempotent, so it is a no-op on the live DB. Downgrade drops the tables in FK order but NOT the `vector` extension.
   - `0002_users`: `users(id uuid PK DEFAULT gen_random_uuid(), email text NOT NULL UNIQUE, password_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), CHECK (email = lower(email)))`.
   - Alembic is now the only schema owner: remove `init_schema` from the app lifespan and from the `Store` protocol / `PgStore` / `FakeStore`, delete the duplicated `SCHEMA` strings that the baseline replaced. `python -m mnemonic.ingest` must not create tables: on a missing table print "Run: uv run alembic upgrade head".
3. **`src/mnemonic/auth.py`**:
   - `pwdlib` `PasswordHash.recommended()` (argon2id): `hash_password`, `verify_password`, and a module-level `DUMMY_HASH`.
   - JWT with PyJWT: `create_access_token(user_id)` (HS256, claims `sub`, `iat`, `exp`); `decode_token` with `algorithms=["HS256"]` and `options={"require": ["exp", "sub"]}`.
   - `get_current_user` dependency: `OAuth2PasswordBearer(tokenUrl="auth/login")`, then the user is loaded from the DB by `sub`; any failure → 401 `{"detail": "Invalid or expired token"}` with `WWW-Authenticate: Bearer`. Not applied to old endpoints yet.
   - Store (Protocol + `PgStore` + `FakeStore`): `create_user(email, password_hash) -> User` (a `User` dataclass: id, email, created_at) that raises `EmailTaken` on `psycopg.errors.UniqueViolation` (race-safe: no check-then-insert), `get_user_by_email`, `get_user(id)`.
4. **Routes** in `src/mnemonic/routes_auth.py` (`APIRouter(prefix="/auth", tags=["auth"])`, included in `main.py`), with docstrings and response models for OpenAPI:
   - `POST /auth/register` (JSON: `email` EmailStr, `password` 8–128 chars, optional `registration_code`) → 201 `{id, email, created_at}`. Email is stripped + lowercased. 409 if taken. 403 if `REGISTRATION_CODE` is set and the code is missing/wrong (`secrets.compare_digest` on bytes).
   - `POST /auth/login` (`OAuth2PasswordRequestForm`, `username` = email) → `{access_token, token_type: "bearer", expires_in}`. Unknown email and wrong password → the SAME 401 body; when the user is missing, still verify against `DUMMY_HASH`.
   - `GET /auth/me` (Bearer) → the user.
   - Hash / verify run through `asyncio.to_thread` (argon2 is CPU-bound).
   - New per-IP limiter for `/auth/*` (`AUTH_RATE_LIMIT_PER_MINUTE`, default 5) in `security.py` next to the others; add its override in `tests/conftest.py`.
   - CORS: add `Authorization` to `allow_headers` and `PATCH` to `allow_methods`.
5. **Config**: `jwt_secret` (required: the lifespan refuses to start if empty or < 32 chars, like `APP_API_KEY`), `jwt_expire_minutes=1440`, `registration_code=""`, `auth_rate_limit_per_minute=5`. Update `.env.example` (comment how to generate: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`). Fix the tests' settings override so the suite still starts.
6. **Tests** (pytest + FakeStore; all existing 136 must still pass): register ok; duplicate 409; email case-insensitive duplicate 409; bad email 422; short password 422; stored hash starts with `$argon2` and is not the password; login ok and the token decodes to the user id; wrong password 401; unknown email 401 with the same body; `/auth/me` ok / no token 401 / tampered 401 / expired 401 / `alg: none` token 401; registration code required when set (403 without, 201 with); auth rate limit → 429.
7. `scripts/auth_smoke.py BASE_URL`: with `httpx` register (random email) → login → me → prints PASS/FAIL per step. Do NOT start a server to run it.
8. **ADR** `docs/decisions/0004-auth-and-migrations.md` (context, decision, rejected alternatives, consequences), built from the decisions table in `docs/labs/lab-21.md`. `backend/README.md`: how to run `uv run alembic upgrade head`. Tick M1 in `docs/labs/lab-21.md`.
9. Self-check, all must be green: `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest`. Then, against the dev DB: `uv run alembic upgrade head` → `uv run alembic current` → `uv run alembic downgrade -1` → `uv run alembic upgrade head`. Do NOT run `downgrade base`.
10. Report ≤ 20 lines, no diffs: what changed, test count, alembic output (revision ids only), anything skipped. List what the DEVELOPER must do (add `JWT_SECRET` to `backend/.env`, run `scripts/auth_smoke.py`, open `/docs` → Authorize). Then 3–7 bullets "what & why": Alembic baseline idea, argon2 vs plain hash, JWT claims + why `algorithms=[...]`, dummy hash / same 401, race-safe unique insert, why hashing runs in a thread.
