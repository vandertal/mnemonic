# 0005 — Hybrid retrieval: own BM25 index + RRF, and a lexical "I don't know" gate

Date: 2026-11-24 · Status: accepted · Lab: 15 (M2)

## Context

Retrieval was vector-only (bge-small, top-5, answer only if the best cosine similarity >= 0.77).
A short or keyword query ("CORS", "Depends", "response_model") has a weak embedding, so its best
similarity often stays below the threshold and the app says "I don't know" although the answer is
in the knowledge base. On our 10 new keyword queries the vector-only rule answered 6 of 10.

## Decision

- **Own index.** The hand-written engine from M1 (`search/`: positional inverted index, BM25)
  is built in memory from all chunks at startup (about 2.5 s and 27 MB of Python objects for 2203
  chunks; the build runs in a worker thread, the app serves at once) and updated incrementally in
  the same code path that writes the DB (after the commit; a failed write never reaches the index).
- **Fusion = Reciprocal Rank Fusion**, k = 60, of the vector top-20 and the BM25 top-20
  (`mode="any"`); the chat still gets the top-5 and the same `Hit` shape and citations.
  RRF uses ranks only, so cosine similarity and BM25 scores need no calibration.
- **Gate (c).** Answer if the best cosine similarity >= 0.77 (unchanged) OR a retrieved chunk
  contains ALL non-stop query terms (queries with <= 3 such terms) and none of those terms occurs
  in more than 10 % of all chunks. `RETRIEVAL_MODE=vector` bypasses all of it and reproduces the old
  behaviour exactly (a test pins the SQL call). Default is `hybrid`.
- **Ownership.** A chunk is visible if it is shared or owned by the caller. The allowed set
  (cached shared ids + the caller's chunk ids read from the DB) is passed to the engine as
  `allowed_ids` and applied BEFORE ranking; lexical-only hits are then fetched from the DB with the
  ownership filter repeated in SQL, and `/search` re-checks every hit with `get_chunks(ids, user)`.
  `/search/explain` answers 404 for a foreign chunk, identical to a missing one.

Numbers (`docs/labs/lab-15-eval.md`, retrieval only, 2203 chunks, dev DB):

| config | original 7 hit | short answered | off-topic refused (10) | `python` alone |
|---|---|---|---|---|
| vector (gate a) | 7/7 | 6/10 | 10/10 | refused |
| bm25 (gate b) | 6/7 | 10/10 | 10/10 | answered |
| hybrid (gate a) | 7/7 | 6/10 | 10/10 | refused |
| hybrid (gate b) | 7/7 | 10/10 | 10/10 | answered |
| **hybrid (gate c)** | **7/7** | **10/10** | **10/10** | **refused** |

Fusion alone (gate a) does not help the refusal problem: the gate still looks at cosine
similarity. The gain comes from the lexical gate. Gate b also answers `python` (a word in 17 % of
the chunks, so "a chunk has every term" proves nothing); gate c removes that by ignoring common
terms. The 10 % cut-off was chosen on this corpus (968 of 2203 chunks are release notes) and may
need another value elsewhere.

## Alternatives rejected

- **Postgres full-text search.** Would work, but it skips the point of the lab (the engine is the
  deliverable) and ties ranking to SQL (`ts_rank`, no code-aware tokens like `response_model`).
- **Score-weighted fusion** (`a * cosine + b * bm25`). Needs the two scales calibrated and
  re-calibrated whenever the corpus changes; RRF needs no tuning.
- **A reranker model.** Better precision, but another model in RAM on a free instance, and the
  problem here is the refusal gate, not the order of the top-5.

## Trade-offs: lexical vs semantic

- Lexical wins on identifiers and rare exact words (`CORS`, `Depends`, `OAuth2`): an embedding of
  one token is weak, but the token is rare, so its IDF is high.
- Semantic wins on paraphrase ("run something after I send the response" -> background tasks): no
  shared words, so BM25 finds nothing, vectors still do. BM25 alone missed 1 of the 7 original
  questions; the vector side is why hybrid keeps 7/7.
- Lexical noise: a common word ("python", "example") matches thousands of chunks; gate c exists
  for that.

## Consequences

- **RAM:** about 27 MB of Python objects for 2203 chunks (measured with `tracemalloc` on Windows;
  on Render the startup log line reports RSS from `/proc/self/status`). Grows linearly with chunks.
- **Single process.** The index lives in one process; Render runs one worker. With several workers
  each would rebuild on its own and uploads would not reach the others.
- **Rebuilt on every restart** (about 2.5 s here): the DB is the source of truth, nothing to
  migrate or keep consistent on disk. Until it is ready, chat falls back to vector-only and
  `/search` answers 503 with `Retry-After`.
- **No stemming** ("middlewares" does not match "middleware"), **English stop words only**
  (Ukrainian notes are searchable but common Ukrainian words are not dropped).
- **One lock** guards the index; readers take it too (a query is a few ms) instead of a copy of the
  whole index per update.
- If the index update fails after a successful DB commit (should not happen) the error is logged,
  the upload still succeeds, and a restart repairs the index.
