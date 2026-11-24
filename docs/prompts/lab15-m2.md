# Lab 15 — M2 task for Claude Code (autonomous): hybrid retrieval + search API

The developer PRE-APPROVED this plan. Do NOT wait for "ok": print a 5-line plan, then execute. Stop only if blocked or an irreversible decision comes up.
Read first: CLAUDE.md, docs/labs/lab-15.md (decisions table!). Then the files you touch: the RAG retrieval code (find where vector search + the 0.77 threshold + top-5 live), `main.py`, `store.py`, `ingest/`, `schemas.py`, `config.py`, `security.py`, `backend/eval/*`, `backend/tests/{conftest,fakes}.py`, the existing integration tests.
Rules: small Conventional commits, NO AI attribution lines, English code/docs/comments, PowerShell-compatible commands, `uv` only, **no new dependencies**. Never print secrets or DATABASE_URL. Do NOT start servers, do NOT deploy. Dev DB = Neon branch `dev` (from `backend/.env`).
Do NOT commit `.vscode/settings.json` or the root `package-lock.json`.

## Scope
M2 only: the search engine goes into the backend. No frontend (M3).

## Tasks
0. `git branch --show-current` must be `lab-15`.
1. **Index lifecycle** (`src/mnemonic/search_service.py` or similar; the `search/` package stays pure):
   - Build the index from all chunks in the DB at app startup (lifespan), in a worker thread so startup is not blocked longer than needed; log one JSON line: chunks, terms, build seconds, approximate memory (RSS from `/proc/self/status` when available, else `tracemalloc` delta).
   - Incremental: after a successful document ingest add its chunks; after delete remove them. Both inside the same code path that writes to the DB (no drift). If the DB write fails the index is not touched.
   - Thread-safety: one lock around index mutation; reads take no lock or a cheap snapshot — explain the choice in a comment. Single-process assumption stated in the ADR (Render runs one worker).
   - **Ownership:** a chunk is visible if its document is shared (knowledge base) or owned by the current user. Compute the allowed set cheaply (cache shared ids; owner ids from the DB) and pass it as `allowed_ids`. No user may ever see another user's chunk through search, explain, or RAG.
2. **Hybrid retrieval in the RAG** (keep the retrieval interface the chat code already uses):
   - New setting `RETRIEVAL_MODE=vector|bm25|hybrid` (default `hybrid`; `vector` must reproduce today's behaviour exactly — a regression test proves it).
   - Hybrid = Reciprocal Rank Fusion (k=60) of vector top-N and BM25 top-N (`mode="any"`), return the same top-5 shape, `sources`/citations unchanged.
   - **The "I don't know" gate is the risky part.** Today: vector similarity ≥ 0.77. Implement the gate as a small, well-named function and compare these candidates in the eval below: (a) vector gate only; (b) vector gate OR a lexical gate: the chunk matches ALL non-stop query terms (`mode="all"`) when the query has ≤ 3 such terms; (c) your own better idea if the numbers show one. Choose by the table, document why. Off-topic questions must still be refused.
3. **API** (router `routes_search.py`, tags `search`, docstrings + response models, OpenAPI examples):
   - `GET /search?q=&limit=10&mode=all|any&ranker=bm25|tfidf` (Bearer, owner-scoped) → hits `{chunk_id, document, score, snippet: {text, highlights: [[start,end],...]}, matched_terms}`. `limit` 1–50; `q` 1–200 chars; empty/blank → 422.
   - `GET /search/explain?q=&chunk_id=` → per-term tf, df, idf, doc length, contribution, total (teaching mode). Foreign or unknown chunk → 404.
   - Reuse the existing per-IP limiter (not the LLM global budget: search costs no LLM tokens).
4. **Eval ablation** (`backend/eval/retrieval_ablation.py`, retrieval-only: NO LLM calls, runs on the dev DB with the real embedder):
   - Reuse the existing eval questions/expected sources. ADD: ≥ 8 short/keyword queries that must be answered (e.g. `CORS`, `Depends`, `response_model`, `OAuth2`, `BackgroundTasks`, `middleware`, `Pydantic`, `WebSocket`) and ≥ 6 off-topic queries that must be refused (e.g. `weather tomorrow`, `pizza recipe`, `world cup winner`, `python` alone is a judgement call — include it and report what happens).
   - For each mode (vector, bm25, hybrid[a], hybrid[b], …) print a table: retrieval hit rate on the original questions, short-query answered rate, off-topic refused rate. Save it to `docs/labs/lab-15-eval.md` with the date and the config.
   - Acceptance for the chosen default: original retrieval 7/7 not worse, off-topic refused 100 %, short-query answered rate strictly higher than vector-only. If no candidate meets all three, keep `RETRIEVAL_MODE=vector` as default, say so loudly in the report, and still ship the code.
5. **Tests** (pytest + FakeStore; the existing suite must still pass):
   - Unit: RRF on hand-made rankings; each gate; `RETRIEVAL_MODE=vector` identical to old behaviour; incremental add/remove keeps the index equal to a fresh rebuild; `/search` 401 without token, 422 on bad params, limit bounds; `/search/explain` contributions sum to the score.
   - **Ownership matrix (Alice/Bob):** Bob never sees Alice's chunk via `/search`, `/search/explain` (404), nor as a RAG source; deleting Alice's document removes it from search at once.
   - Integration (real Postgres, marked like the others): startup build from the DB; ingest → searchable; delete → gone.
   - Snippet safety: a document containing `<script>` comes back as plain text with offsets, no HTML.
6. `scripts/search_smoke.py BASE_URL` (httpx, like `auth_smoke.py`, mind the 5/min auth limit: register 2 users max): A registers + uploads a tiny markdown with a unique token → A finds it via `/search` → B gets 0 hits for the token → no token = 401 → `/search/explain` for A's chunk works and for B = 404 → `Depends` returns ≥ 1 shared hit. Prints PASS/FAIL per step. Do NOT run it.
7. **ADR** `docs/decisions/0005-hybrid-retrieval.md`: context (vector-only refuses short queries), decision (own index + RRF + the chosen gate), alternatives rejected (Postgres full-text search: skips the lab and ties us to SQL; score-weighted fusion: needs calibration; reranker model: memory), tradeoffs lexical vs semantic with the real numbers, consequences (RAM, single process, no stemming, English stop words only, rebuild on every restart). Tick M2 in `docs/labs/lab-15.md` and `docs/ROADMAP.md`; add `RETRIEVAL_MODE` to `.env.example` and `backend/README.md`.
8. Self-check, all green: `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest` · `uv run pytest -m integration` only if `TEST_DATABASE_URL` is set to a throwaway DB (never the dev or production URL) — otherwise skip and say so. Run `uv run python eval/retrieval_ablation.py` and show the table.
9. Report ≤ 20 lines, no diffs: what changed, test count, the ablation table (compact), the chosen gate and default, index memory + build time, anything skipped. List what the DEVELOPER must do (nothing manual before M3 — deploy happens once, after M3). Then 3–7 bullets "what & why": RRF and why no score calibration, why a separate lexical gate, lexical vs semantic failure modes (synonyms vs identifiers), why the index is rebuilt at startup, how ownership is enforced, why incremental updates sit in the same code path as the DB write.
