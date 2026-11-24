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

**M3 — SPA + close.** [ ]
Search panel with safe highlights and "why this result"; live smoke; README (screenshot, latency, tradeoffs lexical vs semantic, limitations); Reflection; tag `lab-15`.
Check: live URL, a keyword query returns ranked snippets; Reflection rewritten in own words.

## Student tasks

None before M1 (no footage, no accounts). Before M2: check Render → service → Metrics → Memory and note the number.

## Reflection

> Not written yet. Draft at M3 from the real code; the developer rewrites it in own words.
