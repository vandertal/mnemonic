# Lab 22 — SPA Frontend (Mnemonic)

Brief: `../Programming-Practice-Projects/labs/lab-22-spa-frontend.md`. Target: **Standard**, Advanced = 1 small side quest if time allows.

## Key adaptation (defend this)

The brief assumes Lab 21 auth (register/login/JWT). Our track is 31 → **22** → 21, so the backend has no accounts yet.
Auth today = `X-API-Key` (access code) + `session_id` / `owner_id` UUIDs in localStorage (NOT real auth).
So: "register/login/logout" → **access-code gate** (enter code / sign out = clear it). Real login/JWT arrives in lab 21 and the SPA gets a login screen then.
Trade-off to state in README: access code in localStorage is XSS-readable (same class of risk as JWT in localStorage).

## Guide → ours → milestone

| Brief requirement | Ours | M |
|---|---|---|
| Deploy "hello" first | Vite app on Cloudflare Pages/Vercel at start | M1 |
| Routing + protected route | `/chat`, `/documents`, `/flashcards`, `/settings`, 404; gate redirects to `/access` | M1 |
| Login form + validation | Access-code form (zod + react-hook-form) | M1 |
| Auth fetch wrapper, 401 handling | `api/client.ts`: adds `X-API-Key`, 401/403 → gate, network error → typed error | M1 |
| CORS | backend allows SPA origin + `X-API-Key` header | M1 |
| List + create/edit/delete | Documents: list/upload/delete; chat history per session | M1–M2 |
| Toasts, no `alert()` | sonner | M1 |
| Server state, optimistic delete | TanStack Query | M2 |
| Skeletons, pagination | documents list, messages | M2 |
| Responsive 375px, dark/light, palette | Tailwind, theme toggle in `/settings` | M2 |
| Offline/failure UX | "couldn't load — retry", SSE error/abort handled | M2 |
| Make it yours | one aesthetic (default: warm "study notebook") | M3 |
| Lighthouse ≥90 mobile, README, reflection, tag | | M3 |

## Milestones (3, grouped)

**M1 — Skeleton + chat (deploy-first).**
CORS on backend (env `CORS_ORIGINS`), Vite+React+TS+Tailwind, deploy hello, router + gate, api client, chat via fetch-stream SSE (tokens, sources, done, tool, error), citation click → `/chunks/{id}`, toasts.
Check: deployed SPA chats against Render backend; wrong code → gate; backend down → toast, no crash.

**M2 — Documents + flashcards + Standard polish.**
TanStack Query; documents list/upload/delete (optimistic delete with rollback, skeletons, client-side pagination); flashcards screen (`POST /flashcards` from a chat message); settings (theme, sign out); responsive 375px; dark/light w/o flash; field-level validation on upload (type/size).
Check: offline mid-action degrades and recovers; DevTools 375px clean.

**M3 — Make it yours + close.**
Aesthetic pass, favicon + OG tags, Lighthouse mobile ≥90, no console errors, README (live URL, 60s recording, trade-offs, architecture), Reflection answers, ROADMAP/progress, tag `lab-22`.
Optional Advanced (pick ONE, ≤3h): i18n uk/en **or** Cmd+K palette.

## Reflection

> **Draft: the developer must rewrite every answer in their own words** and verify each claim in DevTools before the defense. Written from the real code, not from memory.

### 1. Phone demo
Open the live URL (TODO_LIVE_URL) on the phone, enter the access code, ask a question, tap a citation chip (it scrolls to the source card), open the card (exact passage), upload a small `.md`, delete it. Then press "Make flashcards" under an answer. What to point out: nothing overflows at 375px, the sidebar becomes a drawer (Radix Dialog), the dark/light follows the phone.

### 2. Auth flow, token storage, expiry
There are no accounts yet (lab 21 adds them), so "login" is an **access code**.
- `/access`: the form (react-hook-form + zod) puts the code in storage, then proves it with a cheap call (`GET /sessions/<zero-uuid>/messages`). Only on success does `signIn` flip the auth state and navigate to `/chat`. If the server is unreachable the code is cleared and nobody gets in.
- `api/client.ts` `apiFetch` adds `X-API-Key` to **every** request from `getAccessCode()`.
- **401/403** → the client clears the code, calls the registered `onAuthFailure` (sets `hasAccess=false` in `AuthProvider`), and throws `AuthError`; `RequireAccess` then redirects to `/access`. The client has no React knowledge: the callback is injected.
- **Expiry:** the code never expires by itself. It is a static shared secret, so "expired" means "the server rotated it", and that shows up as a 401. Real expiring tokens + refresh are lab 21.
- Sign out = `clearAccessCode()` (Settings).

### 3. Network tab: upload and chat
**Upload a document:** (a) `OPTIONS /documents` preflight, because the request carries a custom header `X-API-Key` (CORS: the server must answer `Access-Control-Allow-Headers` and the origin); (b) `POST /documents` as `multipart/form-data` with `file` + `owner_id` (the browser sets the boundary; we never set Content-Type); the card shows a spinner while pending; (c) on settle `invalidateQueries(['documents'])` triggers `GET /documents?owner_id=…`, so the list shows server truth.
**Chat:** (a) preflight `OPTIONS /chat` (JSON + custom header); (b) `POST /chat` returns `text/event-stream`: `message` events (tokens), `sources`, optional `tool`, `done` (with `message_id`) or `error`; read with `fetch` + `ReadableStream`, parsed by `api/sse.ts` (not `EventSource`, because `EventSource` cannot POST or send headers); (c) after `sources`, each card requests `GET /chunks/{id}?owner_id=…` for its snippet (one request per chunk: `use-chunk.ts` keeps a module-level promise cache shared by the card and the dialog, and forgets failures); (d) opening the history is `GET /sessions/{id}/messages`.

### 4. Wi-Fi off mid-action
- `OfflineBanner` listens to `online`/`offline` events and shows a warning bar.
- `fetch` rejects with a TypeError → `apiFetch` converts it to `NetworkError` → a translated toast ("Can't reach the server…"). An aborted request (Stop button) is *not* treated as a failure.
- Queries retry up to 2 times only for network/5xx errors (`retryPolicy`), never for 4xx; mutations never retry (a repeated POST/DELETE could duplicate or double-delete). TanStack Query refetches on reconnect, so lists heal themselves.
- Mid-stream: the reader throws, the assistant bubble gets the error state; partial text stays.
- Delete while offline: optimistic removal, the request fails, **rollback** restores the card + toast.
- At `/access`: unreachable server → entry refused, not "let in anyway".

### 5. The stored secret and the trade-off
DevTools → Application → Local Storage → `mnemonic.accessCode`: **plain text**, readable by any script on the origin. Not a JWT (no payload, no expiry). Trade-off: `localStorage` survives reloads and is simple, but XSS can steal it; an `httpOnly` + `Secure` + `SameSite` cookie cannot be read by JS but needs a server-side session and CSRF thinking. Mitigations we have: react-markdown does not render raw HTML (model output is untrusted), no third-party scripts, strict typing of API data. Also stored: `ownerId`/`sessionId` UUIDs (not secrets, not auth), theme, language, flashcard decks.

### 6. Two tabs / a 500 mid-submit
**Two tabs:** the code and UUIDs are shared via `localStorage`, but React state is per tab. Documents have `staleTime` 30 s and no refetch on focus, so tab B can show a stale list. Deleting something already deleted in tab A → server 404 → optimistic rollback + toast, and the `onSettled` invalidate reloads the true list. Signing out in tab A does not update tab B until its next request returns 401 (there is no `storage` event listener: a known gap). Flashcard decks are read once per visit, so the other tab must be revisited.
**500 mid-submit:** upload: the mutation fails once (no auto retry), `toastError` shows the translated message ("The server had a problem"), the form stays usable, and `onSettled` refetches because the server may have saved despite the error. Chat: the `error` bubble in the message; the user can ask again. Queries (GET): 2 retries for 5xx, then the retry button.

### 7. Hardest bug
The **.env / CORS / old-deploy chain**: the deployed SPA kept calling the wrong backend or failing preflight. Causes stacked: `VITE_*` variables are **baked at build time**, so changing them in the dashboard does nothing until a rebuild (the old bundle kept the old URL); the backend only allows origins listed in `CORS_ORIGINS` (the custom `X-API-Key` header forces a preflight, so one wrong origin breaks every call, and the browser reports only a vague "CORS error"); and a stale deploy hid the fix. What we added because of it: `scripts/check-env.mjs` (prints the effective API URL, warns on missing/local), `scripts/smoke.mjs` (tests preflight + 401 + 200 from the SPA's origin), and the README deploy order (deploy SPA → set `CORS_ORIGINS` → redeploy backend). *(Developer: confirm the order of events and add what you actually saw.)*

## Status
- [~] M1 — code done, deployed pending developer
- [~] M2 — done, pending manual check (offline mid-action, 375px, real upload/delete, flashcards on the deployed backend)
- [x] M3 — closed 2026-11-21, tag `lab-22`, Lighthouse mobile ≥90. Open debt: Reflection rewrite, recording, TODO_LIVE_URL. Code done (perf, a11y, meta, README, reflection draft). Pending developer: Lighthouse run, phone check, 60s recording, fill `TODO_LIVE_URL`, rewrite Reflection, tag `lab-22`. Cmd+K palette waiting on the `cmdk` install permission.
