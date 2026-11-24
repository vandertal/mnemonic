# Lab 15 — Mini Search Engine (Mnemonic)

Brief: `../Programming-Practice-Projects/labs/lab-15-mini-search-engine.md`.
Target: **Standard** ("It Ranks"). Advanced: positional index + phrase search, boolean `-term`, teaching mode ("why this result"), web UI, **lexical vs semantic retrieval inside our RAG** (the brief's own extension: "use your inverted index as the retrieval layer for an LLM RAG app… document the tradeoffs").
Branch: `lab-15`.

> Replaces lab 33 in the track (track is now 31 → 22 → 21 → **15** → 34 → 42). This is the second swap in the track; the track picker allows one. Confirm with the instructor. Lab 33 plan files are kept as archive (`docs/labs/lab-33.md`, marked superseded).

## Key adaptation (defend this)

The brief builds a CLI engine over text files. We already have a RAG chat whose retrieval is **vector-only** (bge-small, top-5, threshold 0.77). Known pain: short or keyword queries ("CORS", "Depends") get a refusal, because a short query has a weak embedding similarity. A lexical index is exactly what fixes that.
So: the engine from the brief is built **by hand** as a pure Python package inside the backend (no Postgres full-text search: it would skip the lab), and then used as the second retriever next to pgvector → **hybrid retrieval**. Same data, one new retriever, measured on our existing eval set.

## Decisions (made upfront; recorded as ADR 0005 in M2)

| Topic | Decision | Why / trade-off |
|---|---|---|
| Where | `backend/src/mnemonic/search/` — pure Python, no DB/FastAPI imports | Testable without infra; the part we explain line by line. |
| Index | Positional inverted index: `term → {doc → [positions]}` + doc lengths | Positions give phrase search and snippets; costs more RAM than counts only. |
| Ranking | **BM25** (k1=1.5, b=0.75) as default, **TF-IDF** kept as a baseline | Brief allows "TF-IDF or another match-quality ranking". BM25 = TF-IDF + saturation + length normalisation. Both implemented, compared in the report. |
| Tokenizer | Unicode, casefold, `\w+`; **code-aware**: `response_model` and `OAuth2PasswordBearer` are indexed as the whole token AND its parts (same position) | Our corpus is the FastAPI docs: identifiers are the queries people type. Unicode keeps Ukrainian notes searchable. |
| Stop words | Small English list, removed at index and query time, **positions still advance** | Phrase distances stay correct. No Ukrainian list (limitation). |
| Persistence | Index kept in memory, rebuilt from DB chunks at startup, updated incrementally on ingest/delete; JSON save/load (versioned, atomic write) exists for the CLI and benchmarks | Render disk is ephemeral; the DB is the source of truth. |
| Owner scoping | The engine takes `allowed_ids`; the API computes it from the DB | Index stays global and simple; users never see foreign chunks (same 404 rules as lab 21). |
| Fusion | Reciprocal Rank Fusion (RRF, k=60) of vector top-k and BM25 top-k | No score calibration between cosine and BM25 needed. |
| Refusal ("I don't know") | Decided in M2 by eval ablation (vector-only / BM25-only / hybrid); IDK 3/3 must not regress | The threshold logic is the risky part; numbers decide, not intuition. |
| Highlights | Snippet = text + list of `(start, end)` offsets, never HTML | The SPA renders marks itself → no injected markup (XSS). |
| Stemming | Not in scope (no new dependency) | Listed as a limitation; `snowballstemmer` is the future option. |
| New dependencies | None | Stdlib only. |

## Guide → ours → milestone

| Brief | Ours | M |
|---|---|---|
| Day 2 tokenizer | code-aware unicode tokenizer | M1 |
| Day 3–5 inverted index, counts | positional index, per-doc positions | M1 |
| Day 6 AND search | `mode="all"` (+ `"any"` for RAG), phrase, `-term` | M1 |
| Day 8 stop words | list, positions preserved | M1 |
| Day 9 TF-IDF | TF-IDF + BM25, hand-checked numbers in tests | M1 |
| Day 10 snippets | word-boundary snippets + highlight offsets | M1 |
| Day 11 persistence | versioned JSON, atomic write | M1 |
| Checklist: latency <100 ms, indexing time documented | `--bench` p50/p95 on the FastAPI docs | M1 |
| Extension: with Lab 31 (RAG) | hybrid retrieval, eval ablation, ADR 0005 | M2 |
| Extension: with Lab 21 (REST) | `GET /search` (auth, owner-scoped, rate-limited) + explain | M2 |
| Extension: with Lab 22 (SPA) | search panel with highlights + "why this result" | M3 |
| Make it yours | **Teaching mode**: per-term TF, DF, IDF, contribution | M2–M3 |
| README, recording, Reflection, tag | M3 |

## Milestones (3)

**M1 — The engine (pure Python + CLI).** [x]
Tokenizer, stop words, positional index, BM25 + TF-IDF, AND/any/phrase/`-term`, snippets with offsets, `explain`, persistence, CLI with `--bench`, unit tests.
Check: tests green; CLI answers a keyword query on the FastAPI docs in < 100 ms; bench numbers printed (index time, docs, terms, p50/p95).

**M2 — Hybrid retrieval in the RAG + API.** [x]
Index built from DB chunks at startup + incremental updates; RRF fusion; `GET /search` and `GET /search/explain`; eval ablation with new short-query cases; ADR 0005.
Check: eval table (vector / BM25 / hybrid) — short queries answered, IDK 3/3 and existing keyword/retrieval scores not worse; Render memory before/after measured.
Done: gate (c) + `RETRIEVAL_MODE=hybrid` default; table in `docs/labs/lab-15-eval.md` (retrieval 7/7, short 10/10 vs 6/10, off-topic 10/10); ADR `docs/decisions/0005-hybrid-retrieval.md`. Render memory is still to be read from the startup log line after the deploy (after M3).

**M3 — SPA + close.** [x] code and docs done; the deployment checklist below and the tag are pending.
Search panel with safe highlights and "why this result"; live smoke; README (screenshot, latency, tradeoffs lexical vs semantic, limitations); Reflection; tag `lab-15`.
Check: live URL, a keyword query returns ranked snippets; Reflection rewritten in own words.
Done: `/search` screen (`pages/search-page.tsx`, `features/search/`), `renderHighlights` (code points, 13 tests), the shared chunk viewer (`SourceDialog`), explain table, uk + en strings, README "Search" section.

## Deployment checklist (tick after the deploy)

- [ ] PR `lab-15` → `main` merged after green CI (the integration tests run on a real pgvector for the first time)
- [ ] Render deployed
- [ ] Startup log line shows chunks / terms / build time / RSS — record: `chunks=____ terms=____ build=____ s rss=____ MB`
- [ ] Render Metrics → Memory before / after recorded: `before ____ MB → after ____ MB`
- [ ] `cd backend; uv run python scripts/search_smoke.py <render url>` — all PASS
- [ ] SPA search works on the live URL (`Depends`, `"dependency injection"`, an emoji query)
- [ ] Screenshot saved as `docs/screenshots/search.png`
- [ ] README live URL set (`TODO_LIVE_URL`) and the Render memory row filled in

## Student tasks

None before M1 (no footage, no accounts). Before M2: check Render → service → Metrics → Memory and note the number.

## Reflection

> **DRAFT written by Claude from the real code. The developer MUST rewrite it in their own words before the defense:
> you will be asked follow-up questions, and "the assistant wrote it" is not an answer.**
> Numbers are from `search_cli.py --bench` (159 FastAPI doc files) and `docs/labs/lab-15-eval.md` (2203 chunks).

The brief's questions, answered for *our* engine (`backend/src/mnemonic/search/`):

1. **A word in exactly one document; compare with grep.** The index maps `term → {doc → positions}`
   (`index.py`), so a lookup is one dict access plus scoring one posting list: p50 about 0.7–1.1 ms on 159 files
   (bench). `grep -r` re-reads and scans every file for every query, so its cost grows with corpus size; the index
   pays once at build time (3.4 s for 159 files) and then costs almost nothing per query. Grep also returns lines in
   file order with no ranking, and cannot say "this word is rare, so this match matters".
2. **A multi-word query, how the AND happens.** `parse_query` splits the query into terms, phrases and `-excluded`
   terms (`query.py`). In `engine.py` (`_candidates`) each term becomes the set of doc ids from its posting list;
   `mode="all"` intersects these sets (`set.intersection`), `mode="any"` unites them, and `-term` subtracts its set.
   Only the surviving documents are scored. Stop words are removed from the query, so `the cors` is just `cors`.
3. **TF-IDF in my own words, one result.** Score = sum over query words of *tf × idf*: how often the word is in this
   chunk, times how rare it is across all chunks (`log(N/df)`). BM25 (our default, `ranking.py`) changes two things:
   tf saturates (the 10th repeat adds far less than the 2nd) and the chunk length is normalised (k1=1.5, b=0.75),
   so a long release-notes chunk does not win just by being long. Concrete example for the defense: run
   `search_cli.py --explain 1` (or the "Why this result?" row in the SPA) for `Depends` and read tf, df, idf and
   the contribution of the first hit; the contributions add up to the score exactly (a unit test pins this).
4. **No stop-word filter, demonstrate.** Words like `the`, `is`, `to` are in nearly every chunk: their idf is close
   to 0, but they still bloat the index (huge posting lists), slow `mode="all"` intersections, and with tf-idf on a
   small corpus they add noise. Demo: remove the words from `stopwords.py`, rebuild, compare the index size and the
   query `how to use the` in the CLI. Our stop-word handling keeps *positions* advancing, so phrases stay correct.
5. **Where it breaks.** *Empty document:* `add_document` stores length 0 and no postings; it never matches, and
   BM25's `dl/avgdl` is safe while `avgdl > 0` (the engine returns `[]` when `N == 0`). *Same name twice:*
   `add_document` with an existing id first removes the old version (replace, not duplicate); in the app the ids are
   database chunk ids, which are unique, and identical content is de-duplicated by `content_hash`. *Only stop words:*
   `has_positive` is false, so `search` returns `[]` instead of everything. Known weak spot: `python` alone is refused
   by the chat gate by design.
6. **Indexing pipeline for one document.** Upload → `ingest` splits it into chunks → embeddings are stored in
   Postgres → after the DB commit, `SearchService` calls `add_document(str(chunk_id), text)` → `tokenize` (casefold,
   `\w+`, code-aware: `response_model` becomes the whole token and its parts at the same position; stop words dropped but
   positions kept) → postings and lengths updated → the text and word starts are kept for snippets. At startup the same
   path rebuilds everything from the `chunks` table (about 2.5 s for 2203 chunks).
7. **Hardest bug.** *(Write your own: which bug cost you the most time? Candidates from the history: highlight offsets
   shifting after an emoji — code points vs UTF-16; the lexical gate answering `python`; keeping the index consistent
   when a DB write fails.)*
8. **One billion documents.** The in-memory dict index does not fit. First change: shard the index by term range or
   document range across machines and keep postings on disk with compression (delta + variable-byte), build it in
   batches and merge segments (the Lucene way), and score only the top of each posting list. Then caching of popular
   queries and a two-stage ranker (cheap BM25 recall, expensive rerank). Our single-process, rebuilt-on-restart design
   is exactly what stops working first.

**Extra, specific to our work — defense questions (answer in your own words):**

- **Why BM25 over TF-IDF?** Both are implemented and selectable (`ranker=`). BM25 saturates tf and normalises length;
  our chunks vary a lot in length (release notes vs short sections), and plain TF-IDF favours long chunks with many
  repeats. TF-IDF stays as a baseline that is easy to explain. Be ready to show one query where they order results
  differently.
- **Why RRF?** Cosine similarity (0–1) and BM25 (unbounded) are on different scales. RRF uses only ranks:
  `score = Σ 1 / (60 + rank)`, so no calibration is needed and it does not break when the corpus changes. The cost: it
  ignores *how much* better rank 1 is than rank 2. Measured effect: fusion alone did not fix refusals; the lexical gate
  did (6/10 → 10/10 short queries answered, off-topic still 10/10).
- **How is ownership enforced in search?** In four layers. (1) The index is global, but `SearchService.allowed_ids`
  = cached shared chunk ids + the caller's chunk ids read from the DB, and the engine filters candidates BEFORE
  ranking. (2) Lexical-only hits are fetched from the DB with the ownership filter repeated in SQL. (3) `/search` calls
  `store.get_chunks(ids, user.id)` and drops anything the DB does not return. (4) `/search/explain` answers 404 for a
  foreign chunk, identical to a missing one, so ids cannot be probed. Tests: `tests/test_search_api.py` (ownership
  matrix) and `tests/integration/test_pg_search.py` (real Postgres).
