# Lab 42 — M1: paperwork and packaging (no new product code)

Autonomous task. Do NOT wait for "ok". Read `CLAUDE.md`, `docs/labs/lab-34.md`, `docs/labs/lab-31.md`, `lab-22.md`, `lab-21.md`, `lab-15.md`,
`README.md`, and the brief `../Programming-Practice-Projects/labs/lab-42-life-the-universe-and-everything.md` first.
Branch `lab42-m1` from main, small Conventional Commits, no AI attribution lines. Open a PR at the end (do not merge). No new dependencies.

Path A (Synthesis): the answer is Mnemonic = labs 31 (RAG) + 22 (SPA) + 21 (accounts/API) + 15 (own search engine) + 34 (capstone, Telegram bot).
Use ONLY facts found in the repo. Do not invent users, numbers, quotes or feedback. Anything personal -> `TODO_STUDENT:` marker.

## A. `MANIFESTO.md` (repo root, brief's template exactly)
Sections: The Question / The Premise / The Stack / The Constraints / The Answer (`> 42` then one line with the live URLs).
Default question (student will rewrite in his own words, mark with one `TODO_STUDENT` line at the top):
"Can a student trust an AI that explains their own notes, because every sentence of its answer can be checked against the source?"
Premise: 2-3 paragraphs (generic chatbots invent and hide sources; plain search finds words, not answers; flashcards by hand are slow).
Constraints = real ones from `docs/PRODUCT.md` and ADRs (no mobile app, no payments, no own LLM, one ready knowledge base, English embedder, free-tier limits).

## B. README top
Reorder the top: title + 10-word tagline, hero line with live links (web + Telegram), demo video placeholder (`TODO_STUDENT`),
embedded short Manifesto (Question + Answer), Quickstart from a fresh clone (verify every command exists in the repo and in CLAUDE.md),
architecture diagram (keep the existing mermaid), a "Don't Panic" box (cold start ~1 min on free Render, 512 MB memory limit,
English-only questions work best, rate limits), and a table "which lab gave what" (31, 22, 21, 15, 34). Keep the rest of the README as is.

## C. `docs/RETRO.md` (draft from the repo)
What worked / what did not / what I would do differently / which labs flowed in / honest limitations. Build it from `docs/labs/*.md`,
ADRs, the failures table and git history (`git log --oneline`). Concrete items only (e.g. hybrid retrieval gate, deploy lessons, OOM).
Mark the personal parts that only the student can say with `TODO_STUDENT:`.

## D. Packaging
- `LICENSE` MIT, year 2026, holder = `git config user.name`.
- `CONTRIBUTING.md` (short: setup, run tests, commit style, PR flow), link it from README.
- `docs/labs/lab-42.md`: the brief's submission checklist with status per item (done / needs human) and the 7 defense questions
  with a 1-2 line fact sheet for each from the repo. Do NOT write Reflection answers in first person; only facts and pointers.
- Tick lab 42 progress in `docs/ROADMAP.md`.

## E. Known issues (document, small)
- README limitations + failures table: "free Render has 512 MB; one out-of-memory restart was observed on the first Telegram message during a cold start".
- `/cards` in the Telegram bot replies that the model cannot create flashcards in a real chat. Timebox 15 minutes of code reading only
  (no live API): if the cause is obvious (e.g. which question/context it uses, JSON parsing, refusal handling), fix it with a test;
  otherwise write it in the limitations and leave it.

## Self-check
`uv run ruff check . ; uv run pytest` (backend) and `npx tsc -b ; npx oxlint ; npm run build` (frontend) if anything outside docs changed.
Grep your own new files for invented facts: every number must come from the repo.

## Report (<= 15 lines)
Files created, what is still `TODO_STUDENT` (list), what happened with `/cards`, anything skipped and why.
