# Lab 34 — FIX 1: bugs found in live testing

Autonomous task. Do NOT wait for "ok". Read `CLAUDE.md`, `docs/labs/lab-34-failures.md`, `backend/src/mnemonic/answering.py` first.
Branch `lab34-fix1` from main, small Conventional Commits, no AI attribution lines. PR at the end (do not merge). No new dependencies.
Fix root causes, with a test for each. If a cause cannot be found by reading code + local runs, say so in the report; do not guess-patch.
The dev `backend/.env` has a real GEMINI key: you may run a few real calls locally, keep them minimal (free tier, GLOBAL_RPM=5).

## A. Flashcards fail everywhere (web "Make flashcards" and Telegram /cards): 502 "model could not create"
Reproduce locally with a small script against the real model (the same function the routes use). Find the real cause
(model name / response schema or JSON mode / truncated JSON / max output tokens / refusal / context from the last answer / a regression from the `answering.py` refactor).
Fix it, add a regression test (mock the provider with the failing shape you found), and make the 502 message distinguish
"model returned invalid output" from "provider unavailable". Flashcards worked in labs 31/22, so check git history of that function.

## B. Chat answers sometimes die mid-stream ("The model couldn't finish the answer")
Seen live: text starts, then the SSE `error` event; the same question works on retry. Free-tier Gemini is flaky, so make it resilient:
- Classify provider errors (quota/429, overloaded/503, safety/blocked, timeout, other) and log the class into `llm_calls` (if a column is missing add a migration `0006`).
  Show distinct short user messages (quota vs temporary overload vs generic) on web and in the bot.
- If the stream fails: retry ONCE automatically (if text was already sent, tell the client to discard the partial text via a small SSE event, e.g. `reset`, then stream again).
  The final failure keeps today's behaviour. Add a "Try again" button on the error state in the chat UI that re-sends the last question.
- `GET /admin/stats`: add `llm_errors_by_class` for the last 7 days so we can see what really fails in production.
- Tests for classification, the single retry, and the `reset` handling on the client.

## C. After deleting the account, registering/logging in stopped working
Reported: register -> everything fine -> deleted the account (DELETE /auth/me) -> afterwards registration and login fail (also with the same email).
Reproduce with an integration test (register -> delete -> register same email -> login), and check: every FK to `users` (sessions, messages, documents,
llm_calls, events, telegram_accounts) has ON DELETE CASCADE or SET NULL as intended; what DELETE actually returns; the frontend clears the token,
query cache and localStorage after deletion; the register/login error mapping (409/401/429 must read sensibly). Note the `/auth/*` limit is 5/min/IP:
if repeated tests can trigger it, make sure the UI shows the 429 countdown on those screens. Fix what you find.

## D. Auth screens have no way back to the landing page
Add the logo/"Back to home" link to `/` on login and register screens (visible, accessible, uk+en). Logged-in users must still go to the app, not the landing.

## E. Non-English questions
The knowledge base and embedder are English. A Russian/Ukrainian question currently ends in a bare "I don't know".
Before retrieval, if the question is mostly non-Latin letters, skip embeddings and the LLM and return the refusal with reason `non_english`;
the web shows a localized hint ("Ask in English: the knowledge base is in English"), the bot shows the same hint. Event props: `refused=true`, `reason=non_english`.
Tests for detection (mixed text with code identifiers must NOT trigger it).

## F. Docs
Update `docs/labs/lab-34-failures.md` (new rows) and README limitations; mention the free-tier flakiness and the retry design in a short ADR `0008-llm-resilience.md`.

## Self-check
`uv run ruff check . ; uv run ruff format --check . ; uv run pytest` and `npx tsc -b ; npx oxlint ; npm run build ; npx vitest run --pool=vmThreads`.

## Report (<= 15 lines)
For A and C: the actual root cause in one sentence each. What was done for B, D, E, test counts, new env/migrations, anything unresolved.
