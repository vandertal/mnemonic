# 0006 — Capstone metrics: our own events table, no third-party analytics

Date: 2026-11-24 · Status: accepted · Lab: 34 (M1)

## Context

Lab 34 asks for at least one tracked metric. The metric must answer one question: **do real people
get the thing the product promises?** For Mnemonic that is "asked a question and got a cited
answer" (the main action). We also want a cost per active user, and we must not collect what we
do not need: questions are study material and can be personal.

## Decision

- **A table in our own Postgres**, migration `0004`: `events(id, user_id nullable, name, props jsonb, created_at)`.
  Raw SQL like the earlier migrations; two indexes (`name, created_at` and `user_id`).
- **Four events, written on the server only**: `signup`, `question_answered`
  (props `cited`, `refused`), `cards_made`, `search` (prop `results`). The browser sends nothing,
  so an ad blocker or a closed tab cannot lose or fake an event.
- **The main-action metric** is `question_answered` with `cited = true`: the share of registered
  users who got at least one cited answer. A refusal ("not in your materials") is still an
  event, so the dashboard shows how often the product says "I don't know" — also honest data.
- **Never the content.** No question text, no email, no filename, no IP in `props`. The helper
  takes only boolean keyword arguments. A test asserts that the question text is absent.
- **Best effort.** `events.emit` catches every exception and logs it: a broken metrics table must
  never break signup, chat or search (tested with a store whose event writes raise).
- **`user_id ON DELETE SET NULL`**: when an account is deleted the counts stay but the link to the
  person is cut (integration-tested). Deleting an account really deletes the person.
- **`GET /admin/stats`**: Bearer token, allowed only for the emails in `ADMIN_EMAILS`; everyone
  else gets 404 (the route does not reveal itself), no token gets 401. Hidden from OpenAPI.
  Returns totals, distinct users, the last 7 days per day, the main-action rate and LLM cost per
  active user from the existing `llm_calls` table (`cost_usd`, which is 0 on the free tier
  until `PRICE_IN_PER_M` / `PRICE_OUT_PER_M` are set).

## Why not Google Analytics / Plausible / PostHog

| | Own table | Third-party analytics |
|---|---|---|
| Privacy | Data never leaves our database; we choose every field. | A script on the page, cookies or fingerprints, a consent banner, data on someone else's servers. |
| New dependencies and services | None (one table, one query). | A new service, an account, a key, a script, a CSP change. CLAUDE.md: no new service without a reason. |
| The question we need | Exact: "cited answer per registered user", joined with `llm_calls` for cost. | Page views and sessions; the main action needs custom events and still cannot join our cost table. |
| Reliability | Server-side: not blocked by ad blockers. | Blocked for a large part of a student audience. |
| Effort | About 100 lines and tests. | Small to set up, but we would still need our own cost numbers. |

## Consequences

- No visit or page-view counts (the landing page has no tracking). If wanted later, count
  `GET /` hits at the CDN or add one more server event, still without third parties.
- The stats query scans the table: fine for thousands of rows; add a rollup table if it ever grows.
- Events are not retroactive: numbers start from the deploy of migration `0004`.
- The metric is per registered user, so it is only meaningful once real users exist (M3).
