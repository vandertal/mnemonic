# Retrospective — Mnemonic (lab 42)

> **DRAFT built from the repo** (`docs/labs/*.md`, ADRs, the failures table, `git log`). Facts are from the repo;
> the personal parts are marked `TODO_STUDENT:` and only the student can write them.

## Which labs flowed in

| Lab | What flowed into Mnemonic |
|---|---|
| 31 LLM RAG | The core: chunking, local embeddings, pgvector search, streaming cited answers, the "I don't know" gate, flashcards, an eval set. |
| 22 SPA | The React app on Cloudflare: chat, documents, flashcards, uk / en. |
| 21 REST + auth | Accounts, ownership of every row, migrations, integration tests, CI that gates the deploy. |
| 15 Search engine | The hand-written BM25 index, now the second retriever next to pgvector; the `/search` screen. |
| 34 Capstone | Landing page, onboarding, failure audit (33 rows), one metric, the Telegram bot. |

Lab 33 was swapped for lab 15 (plan archived in `docs/labs/lab-33.md`).

## What worked

- **A threshold chosen on data.** The "I don't know" cut-off (0.77) came from measuring on-topic (min 0.808) and
  off-topic (max 0.739) questions, not from a guess. Refusals cost no LLM call.
- **The hybrid retrieval gate, decided by an ablation.** Five configurations were run on the same questions
  ([lab-15-eval.md](labs/lab-15-eval.md)). Gate (c) answered 10/10 short keyword queries (vector only: 6/10), kept 10/10
  off-topic refusals, and still refused `python` alone. The numbers picked it, not intuition ([ADR 0005](decisions/0005-hybrid-retrieval.md)).
- **fastembed (ONNX) instead of PyTorch** to fit the 512 MB free tier: about 250 MB measured locally with the model
  loaded ([ADR 0001](decisions/0001-fastembed-over-sentence-transformers.md)).
- **Deploy gated by CI.** Render deploys `main` only after checks pass (`autoDeployTrigger: checksPass`); integration
  tests run on real Postgres + pgvector.
- **One answering path for two clients.** The chat and flashcards logic moved into `answering.py` so the Telegram bot
  reuses it instead of copying it ([ADR 0007](decisions/0007-telegram-client.md)).
- **Writing failures down.** The failure audit found 10 gaps in M1 and fixed them, e.g. `Retry-After` was invisible to the
  browser because CORS did not expose it, and a lone surrogate in a question turned a 422 into a 500.
- **Honest benchmark.** RAG vs the plain model showed the plain model was not worse on keywords (93 % vs 100 %) because it
  has seen the public FastAPI docs; RAG's value is checkable sources and scope (7/7 vs 0/7 answers with sources, 3/3 vs 0/3 honest refusals).

## What did not work

- **Short queries and the vector-only gate.** A prefix and adding the previous question were both tried and did not give a
  clean gap between on-topic and off-topic; only a lexical signal fixed it (lab 31 notes, then lab 15).
- **Render out-of-memory restart.** One restart on the first Telegram message during a cold start on the 512 MB plan;
  observed, not measured or fixed.
- **Telegram `/cards`.** In a real chat the bot said the model could not make flashcards. Code reading found no cause
  (same function as the web); see [lab-34-failures.md](labs/lab-34-failures.md), row 32.
- **The eval is small.** 10 questions, keyword checks, one run: one question is 10 points, so it is a smoke test, not a benchmark.
- **Deploy chain surprises.** `VITE_*` variables are baked in at build time and CORS needs the exact origin; the old
  bundle kept calling the wrong backend until a rebuild (lab 22 notes). The destructive migration `0003` had to be run on a Neon `dev` branch first (lab 21 notes).
- **A bug found late in tests.** The SSE parser split a CRLF across two network chunks (found in lab 21 M4).
- **Real users never got measured here.** The tracking machinery exists (ADR 0006), but at the time of writing there are no numbers.
  TODO_STUDENT: update this line if users have tried it since.

## What I would do differently

Drawn from the repo's own open items; the reasons are the student's to write.

- Measure memory on Render before adding the search index and the bot, not after (the README row is still empty).
- Start recruiting users (lab 34 M3) before building features, and use the Telegram link as the first ask.
- Build a larger eval set early and add an LLM-judge or hand-checked answers.
- Run the app in a browser on real phones earlier (the landing page and banners were verified only by unit tests).
- TODO_STUDENT: what you would change in how you worked (planning, the AI assistant, time).

## Honest limitations

Full lists are in the README ("Honest limitations", "Telegram bot", "Search"). The ones that matter most:

- Free tiers: Render sleeps after 15 minutes (first request up to a minute) and has 512 MB; Gemini is rationed to about 5 calls/min for the whole service.
- English-only embedder and knowledge base; a Ukrainian question may be refused; no stemming in the search engine.
- One shared knowledge base in Telegram (no uploads); text only.
- The 0.77 threshold and the lexical gate were tuned on one corpus with a small question set, so the evaluation is optimistic.
- No refresh tokens or token revocation; the token is in `localStorage`; rate limiters are in memory.
- Flashcard decks live in the browser only (not synced).
- Open bugs: `/cards` in Telegram; the one out-of-memory restart.

## Personal

- TODO_STUDENT: the moment a prior lab "clicked" into this project.
- TODO_STUDENT: what you enjoyed and what you did not.
- TODO_STUDENT: what real users did and said (if any) and what you changed.
- TODO_STUDENT: what you would cut from the program (honestly).
- TODO_STUDENT: what is next: maintain it or let it end.
