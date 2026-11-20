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

## Reflection prep (fill in M3)
1. Phone demo · 2. Auth flow/token storage/expiry (ours: access code, no expiry — and why) · 3. Network tab on create · 4. Wi-Fi off mid-action · 5. Show stored secret + trade-off · 6. Two tabs / 500 mid-submit · 7. Hardest bug.

## Status
- [~] M1 — code done, deployed pending developer
- [~] M2 — done, pending manual check (offline mid-action, 375px, real upload/delete, flashcards on the deployed backend)
- [ ] M3
