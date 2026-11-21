# 0004 — Accounts, JWT and Alembic migrations

Status: accepted (lab 21, M1)

## Context

Lab 31 shipped a deployed API with fake auth: one shared `X-API-Key` and `owner_id` / `session_id`
UUIDs generated in the browser. Anyone who knows a UUID reads that space. The schema was created
by `init_schema` at every app startup (idempotent SQL, no history). Lab 21 needs real accounts and
versioned migrations. M1 adds both without changing the existing endpoints (M2 does that).

## Decision

| Topic | Decision |
|---|---|
| Migrations | Alembic with **raw SQL** (`op.execute`), no ORM metadata. `env.py` takes the URL from `get_settings().database_url` and rewrites `postgresql://` to `postgresql+psycopg://`. |
| Baseline | `0001` = the exact current schema, all `IF NOT EXISTS`: a no-op on the live DB, a full build on an empty one. Downgrade drops tables in FK order, not the `vector` extension. Alembic is the only schema owner; `init_schema` is gone from the app. |
| Users | `0002`: `users(id uuid, email unique, password_hash, created_at)` with `CHECK (email = lower(email))`. |
| Password hash | argon2id via `pwdlib` (`PasswordHash.recommended()`), run in `asyncio.to_thread` because it is CPU-bound. |
| Token | JWT HS256, 24 h, claims `sub`, `iat`, `exp`. Decoded with explicit `algorithms=["HS256"]` and required `exp`, `sub`. `JWT_SECRET` is mandatory (>= 32 chars), the app refuses to start without it. |
| Login | OAuth2 password form (`username` = email), so Swagger's Authorize button works. |
| Login errors | Unknown email and wrong password give the same 401; a dummy hash is verified when the user is missing (no enumeration by message or timing). Register still answers 409 for a taken email: accepted. |
| Duplicate email | The UNIQUE constraint decides; `UniqueViolation` becomes `EmailTaken`. No check-then-insert (race-safe). |
| Registration | Open, plus optional `REGISTRATION_CODE`; a stricter per-IP limit (`AUTH_RATE_LIMIT_PER_MINUTE`, 5) on `/auth/*`. |
| Token storage in the SPA | localStorage (XSS-readable; same trade-off as lab 22). |

## Rejected alternatives

- **SQLAlchemy ORM + autogenerate**: rewriting the tested psycopg `store.py` adds no product value.
- **passlib / python-jose**: unmaintained; FastAPI docs moved to pwdlib + PyJWT.
- **bcrypt / plain SHA-256**: SHA is fast by design, so brute force is cheap; argon2id is memory-hard.
- **HttpOnly cookie**: SPA and API are on different origins, which brings SameSite/CSRF complexity.
- **Keeping `init_schema` next to Alembic**: two schema owners drift apart.
- **Refresh tokens / server-side revocation**: out of scope; logout = the client forgets the token.

## Consequences

- Deploys must run `uv run alembic upgrade head` (wired into Render in M3).
- No autogenerate: every schema change is hand-written SQL in a new revision.
- A leaked `JWT_SECRET` lets anyone forge tokens; rotating it logs everyone out.
- Tokens cannot be revoked before they expire (up to 24 h).
- `X-API-Key` and `owner_id` still work until M2.
