# 0007 — Telegram bot: a second client inside the same service

Date: 2026-11-24 · Status: accepted · Lab: 34 (M5)

## Context

Real users (lab 34, M3) are easiest to get where they already are: a chat app. A student will send
one message to a bot sooner than register on a website. The bot must be a **second client of the
same backend**: the same RAG, the same citations and "I don't know" gate, the same limits and
events. A second copy of the RAG logic would drift and double the bugs.

## Decision

- **Webhook inside the existing FastAPI service** (`POST /telegram/webhook/{secret}`), not a
  separate worker with long polling. One deployment, one database connection setup, one set of
  env vars, and it fits the free tier (Render sleeps; a webhook request wakes it, a polling loop
  would have to be woken by something else). Telegram retries a slow webhook, so the route answers
  `200` at once and the work runs in a background task; a small in-memory LRU (1000 `update_id`s)
  drops the retries.
- **No duplicated RAG.** The chat route and the flashcards route were split into
  `answering.start_answer` / `answering.make_flashcards`; the routes and the bot both call them.
  The bot folds the SSE stream into one final answer (`collect_answer`) because a Telegram message
  is sent once, not token by token. Retrieval, `is_answerable`, the service-wide LLM budget,
  `llm_calls` and the `question_answered` / `cards_made` events behave exactly as on the web; the
  events carry `channel = "telegram"` (no `channel` = web), and `GET /admin/stats` gained a
  `by_channel` breakdown.
- **aiogram 3.x (the `Bot` client and its typed API), not `python-telegram-bot`, not raw
  `httpx`.** Reasons: it is async-first like FastAPI (no thread bridge), its `Bot` is one pooled
  session with typed methods and flood-control errors as exceptions, and a webhook is a first-class
  mode. We deliberately do **not** use its `Dispatcher` / FSM: conversation state lives in
  Postgres (the chat session), and the route parses the small `Update` dict itself, so the bot
  logic is plain Python over a 5-method `TelegramApi` interface and is tested with a fake, never
  with the network. Only `telegram_api.py` imports aiogram, and only when a token is set.
- **Identity without passwords.** Migration `0005`: `telegram_accounts(telegram_id bigint PK,
  user_id → users ON DELETE CASCADE)`. The first message from a Telegram id creates a normal user
  `tg-<id>@telegram.invalid` (a reserved TLD: never a real mailbox) with an **argon2 hash of a
  random secret that is never stored or shown**, so the account cannot be logged into on the web
  (a login attempt is a clean 401, not an error). Creation is serialised per Telegram id with
  `pg_advisory_xact_lock`, so a burst of first messages yields one user and one `signup` event.
  Because it is a normal user, ownership, limits, and "delete the account removes everything"
  (cascade) need no special cases.
- **The chat session is "the newest one".** No column for the current session: the bot uses the
  person's most recently used session, and `/new` creates an empty one. Memory works exactly like
  the web (the last turns go into the prompt).
- **Output safety.** `parse_mode=HTML`; every piece of model output, source name and card text goes
  through `html.escape`. Only our own `<b>` / `<code>` tags are added (from the model's `**` and
  backticks). Messages over 4096 characters are split on paragraph boundaries, measured on the
  *escaped* length and cut before escaping so an entity is never split.
- **Privacy.** No question text in events or logs: failures log the exception type and stack
  frames, not its message (messages can carry user text). The token and the webhook URL (it
  contains the secret) are never logged.

## Webhook security

Two secrets must match, both compared with `hmac.compare_digest` and **both always evaluated**:
the one in the path and the `X-Telegram-Bot-Api-Secret-Token` header (Telegram adds it because we
pass the same value to `setWebhook`). Any mismatch, or an unset token/secret, is a `404`, so the
route does not reveal itself. Groups and bot senders are ignored (a shared chat must not become one
person's account), and only `message` and `callback_query` updates are requested.

## Risks and what we accepted

| Risk | Handling |
|---|---|
| The secret is in the URL path, so uvicorn's access log line contains it. | The header is a second, independent factor; the app's own JSON access log uses the route template. Render logs are visible only to the owner. Rotate by changing `TELEGRAM_WEBHOOK_SECRET` and redeploying (the webhook is re-registered on start). |
| In-memory dedupe and per-person limiter are per process and reset on restart. | Single instance on the free tier; the worst case is one repeated answer after a restart. |
| Background tasks die with the process: a deploy during an answer loses it. | Telegram does not retry (we returned 200); the person sees nothing and asks again. Acceptable for an MVP. |
| Free-tier cold start: the first webhook after a sleep takes up to a minute. | Telegram retries and the dedupe absorbs it; documented in the README. |
| One shared knowledge base, text only, no uploads from Telegram. | Documented limitation; uploads stay on the web (and the web cannot log in as a Telegram user). |
| Telegram sees the questions (it is the transport), and Gemini sees them as on the web. | Stated in the README privacy note. |
| `/cards` and questions spend the same global LLM budget as the web. | Intended: one budget, one billing limit. A busy service answers with a friendly one-liner. |
| A new dependency. | `aiogram` only, approved for this milestone; it pulls `aiohttp`, `pydantic` (already used) and a few small packages. |

## Consequences

- The app still starts and passes every test with no Telegram settings (`TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_URL` all optional). Without a token the route is a `404`.
- `main.py` got smaller: the answering core lives in `answering.py` and any future client (an
  email bot, a CLI) calls the same two functions.
- The "web vs Telegram" split in `/admin/stats` answers the M3 question "where do real users
  come from".
- Not done on purpose: a `/delete` command (delete-account stays a web feature and the Telegram
  account has no web login, so for now it is an owner action: delete the `users` row, the cascade
  removes the rest), photos/voice, inline mode, group chats, streaming edits of one message.
