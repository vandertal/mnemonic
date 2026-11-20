# Lab 22 — M2 task for Claude Code (autonomous)

The developer PRE-APPROVED this plan and the new dependency (TanStack Query). Do NOT wait for "ok": print a 6-line plan, then execute everything below in order, self-checking as you go. Stop and ask ONLY if blocked by a missing secret or an irreversible decision.

Read first: CLAUDE.md, docs/labs/lab-22.md, backend `main.py` + `schemas.py` (real shapes of /documents and /flashcards), then only the frontend files you touch.
Rules: small Conventional commits, no AI attribution lines, English code/comments/docs, all UI strings via i18n (uk + en).

## 0. Guards against last time's bugs (do first)
- `frontend/.env.example`: `VITE_API_URL=https://mnemonic-y1js.onrender.com` and `VITE_MAX_UPLOAD_MB=1`.
- `frontend/scripts/check-env.mjs` + `"predev"` script: print the effective API URL; print a loud warning if `VITE_API_URL` is missing or points to 127.0.0.1/localhost. Warning only, do not fail.
- `frontend/scripts/smoke.mjs` + `"smoke"` script (plain Node 20+ fetch, no new deps). Reads API URL from env/.env, key from `SMOKE_KEY`, origin from `SMOKE_ORIGIN` (default http://localhost:5173). Checks, one line each (PASS/FAIL), exit 1 on any FAIL, never print the key:
  1. OPTIONS /chat with Origin + Access-Control-Request-Headers x-api-key,content-type -> 200 and allow-origin equals origin.
  2. GET /sessions/<zero-uuid>/messages with a wrong key -> 401.
  3. Same with SMOKE_KEY -> 200.
  4. GET /documents for a random owner_id with the key -> 200 (use the real query shape from main.py).
  Add a "Commands" note about smoke in frontend/README.md.

## 1. Chat sessions
- "New chat" button (sidebar + mobile drawer) = new session_id UUID, becomes active.
- Session list in localStorage (id, title = first question trimmed to ~40 chars, updatedAt); switch, delete locally, active one highlighted; sorted by updatedAt. History loads for the active session. Delete of the active session creates a new one.

## 2. Documents page (TanStack Query)
- GET/POST/DELETE /documents via the api client; QueryClient with sensible retry (no retry on 4xx).
- Skeleton list, empty state, card per document (name, size/chunks if returned, date).
- Upload: drag-and-drop + button, client validation BEFORE sending: allowed types from backend, size <= VITE_MAX_UPLOAD_MB, max 5 documents; field-level i18n error messages; pending state while uploading; success/error toast.
- Delete: OPTIMISTIC (remove from cache instantly, roll back on error + toast), with a confirm dialog.

## 3. Flashcards
- "Make flashcards" button on each finished assistant message (needs message_id from the `done` event; for history messages use the stored id). POST /flashcards {session_id, message_id, owner_id}. Check the real response shape first.
- Decks persisted in localStorage per owner (deck = source question + cards). Flashcards page: deck list with "load more" pagination (page size 6), card grid, and a review mode: flip-to-reveal, prev/next, keyboard arrows + space, progress indicator. Empty state explains how to create cards.

## 4. Gate + offline
- /access: when the server is unreachable do NOT let the user in; stay on /access, show a toast with retry hint.
- Offline banner via navigator.onLine (online/offline events), i18n.

## 5. Citations
- In answers, `[n]` and `[2, 3, 4]` render as small accent chips linking/scrolling to the matching source card (hover title). Existing renumbering logic stays.

## 6. Finish
- Run tsc, oxlint, `vite build`, backend `ruff` + `pytest` if backend files changed; fix everything.
- In docs/labs/lab-22.md tick M1 as "code done, deployed pending developer" and M2 as done-pending-manual-check; `git add` docs/labs/lab-22.md and docs/prompts/*.
- Report <= 20 lines: commits list, what is NOT verified. No diffs, no file dumps.
- Then 3-7 bullets "what & why": TanStack Query cache + optimistic rollback, multipart upload, localStorage persistence trade-off, key= session handling.
