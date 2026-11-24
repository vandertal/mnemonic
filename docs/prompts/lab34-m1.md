# Lab 34 — M1: everything that needs no outside users

Autonomous task. Do NOT wait for "ok". Read `CLAUDE.md`, `docs/PRODUCT.md`, `docs/labs/lab-34.md` first.
Branch `lab34-m1`, small Conventional Commits, no AI attribution lines. Open a PR at the end (do not merge).
No new dependencies without asking (none are expected; use Tailwind/Radix/i18next already present).
Goal: Standard level of lab 34 minus the user-count items. Must look polished, like a top AI product.

## A. Landing page (frontend, route `/` for logged-out users; logged-in -> app)
- One sentence hero + one "Try it" button (-> register) + secondary "Log in". Understandable in 10 seconds.
- A product visual in the hero: a static, hand-built mock of the chat showing a streamed answer with citation chips
  (pure JSX/Tailwind, no image file needed; no dangerouslySetInnerHTML).
- Below: 3 steps (Ask -> Verify the source -> Make cards), 3 feature cards (cited answers / honest "not in your materials" /
  hybrid search with "Why this result?"), short privacy note, footer with GitHub link.
- uk + en via react-i18next, dark/light themes, responsive (mobile 375px), accessible (landmarks, focus, contrast).
- `<title>`, meta description, og tags consistent with existing `VITE_SITE_URL`.
- Keep Lighthouse >= 90 (no heavy assets, no layout shift).

## B. Onboarding < 60 s without instructions
- After register/login the user lands on chat with the FastAPI knowledge base ready and an empty state:
  3 clickable example questions that send immediately (take them from `docs/labs/lab-15-eval.md` or lab-31 eval set, real ones).
- After the first answer with citations show one subtle hint pointing to "Make cards" (dismiss once, remember in localStorage per user id).
- Cold start: if the API takes > 4 s show a calm banner "Server is waking up (free tier), up to a minute" with elapsed time; clear it on success.

## C. Graceful failures (audit + fix)
Write `docs/labs/lab-34-failures.md`: table "situation -> what the user sees -> status (ok/fixed)". Cover at least:
offline (navigator.onLine banner + retry), API cold start, 429 (friendly text, retry-after countdown), LLM error/timeout mid-stream,
empty / too-long / weird-unicode question (client + server limits, 422 -> readable message), unsupported or oversized upload,
expired token (401 -> login with toast), empty knowledge base, search with no results. Fix every gap you find; add tests for the server-side ones.

## D. One tracked metric + cost
- Migration `0004`: table `events(id, user_id nullable, name, props jsonb, created_at)`; raw SQL like previous migrations.
- Emit server-side: `signup`, `question_answered` (props: cited true/false, refused true/false) = THE main-action metric,
  `cards_made`, `search`. Never store question text. Failure to write an event must never break the request.
- `GET /admin/stats` (Bearer, allowed only for emails in env `ADMIN_EMAILS`, otherwise 404): totals, distinct users, last 7 days per day,
  main-action rate, and average LLM cost per active user from existing `llm_calls`. Add `ADMIN_EMAILS` to `.env.example` and `render.yaml`.
- Tests (unit + one integration). Update `scripts/` with nothing new unless needed.

## E. README + docs (brief's 14-item list)
Rewrite README top to the order in the lab-34 brief section "What to put in your README": tagline, live link, demo placeholder,
who/what problem, stack, **mermaid architecture diagram**, "What is AI here" (models, prompts location, retrieval, eval numbers from lab-15-eval),
cost per user (from D), run locally, side quests done, honest limitations, privacy/ethics notice.
Put `TODO_STUDENT:` markers ONLY for things a human must provide (60 s video, real user feedback, live screenshots).
Update `docs/labs/lab-34.md` statuses and `docs/ROADMAP.md`. Add ADR `0006-capstone-metrics.md` (why own events table, no third-party analytics).

## Self-check before finishing
`uv run ruff check . ; uv run ruff format --check . ; uv run pytest` (backend), `npx tsc -b ; npx oxlint ; npm run test ; npm run build` (frontend).
Check the landing manually at 375px and 1280px by reading the rendered component tree/tests; state what you could not verify.

## Report (<= 20 lines)
What was done per section A-E, test counts, what needs a human (list), new env vars for Render, anything you skipped and why.
