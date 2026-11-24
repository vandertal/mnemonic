# Lab 34 — failure audit

What the user sees when something goes wrong. Audited on 2026-11-24 (M1).
**ok** = already handled before the audit. **fixed** = a gap found in the audit and closed in M1.
Tests named in the last column pin the behaviour (`backend/tests/…`, `frontend/src/…`).

| # | Situation | What the user sees | Status | Pinned by |
|---|---|---|---|---|
| 1 | **Offline** (browser reports no connection) | A yellow banner "You're offline…" with a **Retry** button (refetches everything; an error toast if still offline). Queries refetch by themselves when the connection returns. | fixed (banner existed; the Retry button is new) | manual |
| 2 | **Sending a question while offline** / server unreachable | The answer bubble shows "Can't reach the server. Check your connection…" with a **Try again** button that re-sends the question. | fixed (no retry before) | `api/errors.test.ts` (dead network → `errors.network`) |
| 3 | **API cold start** (Render free tier sleeps, a request waits > 4 s) | A calm banner "The server is waking up (free tier). This can take up to a minute." with a running timer; it disappears with the first answer. Shown in the app and on login/register. Chat and upload requests are excluded on purpose: a slow LLM is not a sleeping server. | fixed (nothing before) | `lib/cold-start.test.ts` |
| 4 | **429, too many requests** | "The service is busy right now. Try again in N s." In the chat the failed answer has a **Try again** button that is disabled and counts down the server's `Retry-After`. The header is readable by the SPA because CORS now exposes it. | fixed (no countdown; `Retry-After` was invisible to the browser) | `api/errors.test.ts`, `test_cors.py::test_retry_after_is_readable_by_the_browser` |
| 5 | **LLM error or timeout mid-stream** | The partial answer stays on screen; below it "The model couldn't finish the answer. Please try again." and a **Try again** button. The text is in the UI language (the server's English sentence is no longer shown). Server side: idle timeout, provider error and retry are tested; the failed call is still logged. | fixed (English text, no retry) | `test_chat.py::test_chat_reports_provider_failure_as_error_event`, `…times_out_when_model_stalls_mid_answer` |
| 6 | **Connection drops mid-answer** (stream ends without a `done` event) | "The connection dropped while the answer was being written. Try again." + retry. Before, the cut-off answer was silently shown as finished. | fixed | `api/errors.test.ts` (stream ends / breaks → `StreamInterruptedError`) |
| 7 | **Empty question** | The send button is disabled for blank text. If anything slips through: a toast "Type a question first." Server: whitespace-only text is a 422. (Before, `"   "` passed the server check and went to retrieval.) | fixed | `test_chat.py::test_chat_rejects_invalid_body`, `chat/question.test.ts` |
| 8 | **Too-long question** | The textarea stops at 2000 characters and shows a counter from 1800. If a longer text reaches the server: 422, shown as "That is too long. Questions can have up to 2000 characters." Before, the user saw the raw "Unprocessable Content". | fixed | `test_chat.py` (2001 chars → 422), `api/errors.test.ts` |
| 9 | **Weird Unicode**: emoji, CJK, RTL marks, zero-width characters | Work normally. | ok | `test_chat.py::test_chat_accepts_emoji_and_non_latin_text`, `chat/question.test.ts` |
| 10 | **Weird Unicode that breaks storage**: NUL character, a lone surrogate (broken emoji half) | Client strips them before sending. Server: 422 with a readable message. A lone surrogate used to turn the 422 *response itself* into a **500** (FastAPI echoed the bad input back and could not encode it); validation errors no longer echo input. | fixed | `test_chat.py` (NUL, lone surrogate → 422), `chat/question.test.ts` |
| 11 | **Unsupported upload type** | Client check: "This file type isn't supported. Use .md, .txt, .pdf." Server: 415. Disguised files (PDF named .txt, binary, not UTF-8, fake PDF, encrypted, scanned) are 422 with a sentence. | ok | `test_documents.py` |
| 12 | **Oversized upload** | Client check ("larger than N MB") before sending; server: early `Content-Length` check and a real byte check, 413. Page limit and 5-document limit also have messages. | ok | `test_documents.py` |
| 13 | **PDF whose text contains NUL / lone surrogates** | Imported normally (the bad characters are dropped). Before: a 500 at the database INSERT. | fixed | `test_documents.py::test_text_postgres_cannot_store_is_cleaned_not_a_500` |
| 14 | **Expired or invalid token (401)** | Token is removed, caches are cleared, a toast "Your session has ended. Please sign in again." and the login page (the visitor returns to where they were). A wrong password on the login form does *not* log anyone out. | ok | `api/sse.test.ts`, `api/errors.test.ts`, `test_security.py` |
| 15 | **Empty knowledge base / nothing relevant** | The honest refusal card "Not in the knowledge base" with a hint; no LLM call, no cost, saved in history. A new account with no uploads still has the shared FastAPI knowledge base. Documents page: empty state "No documents yet". | ok | `test_chat.py::test_no_hits_at_all_is_also_a_refusal` |
| 16 | **Search with no results** | Empty state "No results" with a tip (fewer words, "Any word"). Stop-word-only query = empty list, not an error. | ok | `test_search_api.py::test_stop_word_only_query_is_an_empty_list_not_an_error` |
| 17 | **Search index still building after a restart** | "The search index is still being built. Try again in a few seconds." (503 + `Retry-After`); the chat falls back to vector search. | ok | `test_search_api.py` |
| 18 | **Server 5xx / unknown error** | "The server had a problem. Please try again." (never a stack trace or raw JSON). | ok | manual |
| 19 | **Chat deleted on another device** | "Chat not found" card with a button back to the latest chat. | ok | manual |
| 20 | **The metrics table is broken** | Nothing: events are written best-effort, the request succeeds. | fixed (new feature, designed this way) | `test_events.py::test_a_broken_events_table_does_not_break_signup_or_chat` |

## Not covered (known, honest)

- The offline banner relies on `navigator.onLine`, which can say "online" on a dead Wi-Fi; the request error path (row 2) covers that case.
- There is no client-side timeout: a request to a sleeping server waits until it wakes (the banner explains why).
- Row 3: the banner is verified by unit tests of the timer logic, not in a real browser in M1.
- A 429 from the *service-wide* LLM budget and from the per-IP limit look the same to the user; both carry a `Retry-After`.
