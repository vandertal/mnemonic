# Lab 34 — AI Capstone: Mnemonic for real users

Brief: `Programming-Practice-Projects/labs/lab-34-ai-capstone.md`. Target: **Standard**, Advanced where cheap.

## Product statement (one problem, one group)

Mnemonic: students who study from a pile of notes/PDFs/docs ask questions and get cited answers
instead of reading everything, then turn them into flashcards.
**Group for the capstone: groupmates / university students.** Main action = "asked a question and got a cited answer".

## Requirements → where we stand

| Brief requirement | Level | Ours | Milestone |
|---|---|---|---|
| ≥1 AI capability (designed by us) | Basic | RAG (lab 31) + own BM25/hybrid retrieval (lab 15: "algorithm with AI-style results" counts) | done |
| Shipping skill from another lab | Basic | SPA (22) + API with accounts (21) | done |
| Deployed publicly | Basic | Render + Cloudflare, live | done |
| 5+ real people not from family | Basic | none yet | M3 |
| Landing page, 10 s (1 shot, 1 sentence, 1 button) | Standard | **done (code)**: `/` for signed-out visitors, JSX chat mock, uk + en; live screenshot + Lighthouse re-check pending | M1 |
| Onboarding < 60 s without instructions | Standard | **done (code)**: 3 tap-to-ask eval questions, one-time "Make cards" hint, cold-start banner; timing with a real person pending (M3) | M1 |
| Graceful failures (offline, model errors, limits, weird input) | Standard | **done**: audit table with 20 rows in [lab-34-failures.md](lab-34-failures.md), 10 gaps fixed, tests added | M1 |
| ≥1 tracked metric | Standard | **done (code)**: `events` table (migration 0004), main action = cited answer, owner-only `GET /admin/stats`, ADR 0006; real numbers pending (M3) | M1 |
| Post-mortem: ≥3 users' real feedback + real changes | Standard | none | M3 |
| 10+ users | Standard | none | M3 |
| Hard billing limit on AI provider | checklist | open since lab 31 | M2 (student) |
| Advanced (pick cheap): eval set exists (lab 15 eval), per-user cost doc, uk/en done | Advanced | eval set ✓, uk/en ✓, README "Cost per user" written (an assumption until real data) | M4 |

## Milestones

- **M1 — Landing + onboarding.** Public `/` landing (sentence, screenshot, "Try it"), after signup a ready knowledge base and 3 clickable example questions, first cited answer in < 60 s.
- **M2 — Failure modes + metric + cost.** Failure audit with a table (what happens when…), events table with main-action metric and a tiny stats endpoint, per-user cost note, hard billing limit.
- **M3 — Users (student-driven, starts NOW in parallel).** 10+ people, watch 3 in person/call, notes in `docs/user-feedback/session1..3.md`, iterations in `iterations.md`.
- **M4 — Close.** README per brief list (14 items), 60 s demo, deployment checklist, tag `lab-34`, Reflection in own words.

- **M5 — Telegram bot (last, after M1).** Second client of the same API: same RAG, citations, flashcards. Also the cheapest way to get real users (M3). Needs a dependency decision (`python-telegram-bot` or `aiogram`) — agreed in the planning chat before coding.

## Update 2026-11-24

M1 (landing, onboarding, failures, metric, README) is one autonomous prompt: `docs/prompts/lab34-m1.md`. M3 (users) stays for the student.

**M1 status: code and docs done on branch `lab34-m1` (PR open, not merged).**

Left for the student (everything else is in the repo):

- [ ] Merge the PR after green CI (the integration tests, incl. `test_pg_events.py` and the changed migration test, run on real Postgres only in CI: there was no local Postgres in M1).
- [ ] Render: add env var **`ADMIN_EMAILS`** (your login email; `sync: false`, so on an existing Blueprint add it by hand). Migration `0004` runs by itself on deploy.
- [ ] Open the live site in a phone-sized window (375 px) and a desktop one: landing, sign-up, the 3 example questions, the Make-cards hint (M1 had no browser to look at pixels).
- [ ] Take the screenshots (`docs/screenshots/landing.png`, `chat.png`) and the 60 s video; set the live SPA URL in the README.
- [ ] Run Lighthouse on `/` (target >= 90); the page adds no images and no fonts beyond the existing ones.
- [ ] M3: recruit 10+ people, watch 3, write `docs/user-feedback/`; then put the real numbers from `GET /admin/stats` into the README ("Cost per user", "What real users said").
- [ ] Hard billing limit at the AI provider (open since lab 31).
- [ ] Rewrite the Reflection in your own words (M4).

## Open / risks

- Real users take calendar time → recruit before M1 is finished.
- Second AI-skill wording in the intro (≥2 from 31/32/33): covered by 31 + 15; confirm 33→15 swap with the instructor.
