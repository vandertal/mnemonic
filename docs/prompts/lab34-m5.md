# Lab 34 — M5: Telegram bot (MVP)

Autonomous task. Do NOT wait for "ok". Read `CLAUDE.md`, `docs/labs/lab-34.md` (M5), `docs/decisions/0006-capstone-metrics.md` first.
Branch `lab34-m5` from main, small Conventional Commits, no AI attribution lines. Open a PR at the end (do not merge).
**Approved dependency: `aiogram` 3.x only** (`uv add aiogram`). Nothing else new.

## Idea
The bot is a second client of the SAME backend: same RAG, citations, flashcards, limits, events.
No duplicated RAG logic: call the same service functions the `POST /chat` and `POST /flashcards` routes use
(collect the stream to a final answer instead of sending SSE).

## Backend
- Config (optional feature, app must run fine without it): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_URL`.
  Add to `.env.example` (empty) and `render.yaml` (`sync: false`).
- Webhook route `POST /telegram/webhook/{secret}`:
  compare path secret AND header `X-Telegram-Bot-Api-Secret-Token` with `hmac.compare_digest`; mismatch -> 404.
  Answer 200 immediately and process the update in a background task (LLM takes seconds; Telegram retries slow webhooks).
  Dedupe by `update_id` (small in-memory LRU, ~1000). Log task exceptions; never crash the app.
- On startup, if token + PUBLIC_URL are set: `set_webhook(url, secret_token=...)` inside try/except (log only). Never log the token.
- Identity: migration `0005` (raw SQL like before): `telegram_accounts(telegram_id bigint primary key, user_id fk users on delete cascade, created_at)`.
  First message from a telegram id creates a normal user `tg-<id>@telegram.invalid` with an unusable random password hash (cannot log in on the web)
  and a row here. Idempotent under concurrent first messages. Emit `signup` (props channel=telegram).
  `DELETE`-me semantics stay the same (cascade).
- Behaviour (parse_mode HTML, always `html.escape` model output; split messages > 4096 chars on paragraph boundary):
  - plain text = a question -> answer + a "Sources" list (`[1] title — path`) or the honest "not in your materials" refusal as is.
    Show typing action while waiting. One chat session per telegram user (memory like the web); `/new` starts a fresh one.
  - `/start` -> 2-line welcome + 3 example questions as inline buttons (same questions as the web onboarding); `/help`.
  - `/cards` -> flashcards (5) for the last answered question, sent as "Q / A" pairs.
  - non-text messages -> short "text questions only" reply. Over-long question -> readable message (same limit as web).
  - 429 / provider error / timeout -> friendly one-liner, same wording style as the web failure table. Never echo raw user input in errors.
- Events: `question_answered` (+ channel=telegram prop), `cards_made`; no question text anywhere (events or logs).
- Add `channel` breakdown to `GET /admin/stats` (web vs telegram).

## Frontend (tiny)
- Optional build var `VITE_TELEGRAM_BOT_URL`; if set, show an "Open in Telegram" link in the landing hero (secondary) and footer. uk+en. Hidden when unset.

## Tests
- Unit with a mocked bot/session: webhook secret checks (path + header), dedupe, message splitting, HTML escaping, identity creation idempotent,
  /start /cards /new, rate-limit and error replies.
- One integration test for migration `0005` + identity (CI runs it on Postgres).

## Docs
- ADR `0007-telegram-client.md` (why webhook inside the same service, why aiogram, identity without passwords, risks).
- README: "Telegram bot" section (what it does, how to create/connect it) + limitations (one shared knowledge base, text only, free-tier cold start delays the first reply).
- Add rows to `docs/labs/lab-34-failures.md`. Tick M5 in `docs/labs/lab-34.md` and `docs/ROADMAP.md`.

## Self-check before finishing
`uv run ruff check . ; uv run ruff format --check . ; uv run pytest` and `npx tsc -b ; npx oxlint ; npm run build ; npx vitest run --pool=vmThreads`.
Do not call the real Telegram API in tests.

## Report (<= 20 lines)
Done per section, test counts, new env vars (names only), the exact human steps to go live
(BotFather, Render env, Cloudflare build var + redeploy), and anything skipped and why.
