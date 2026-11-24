# Lab 15 — retrieval ablation

Date: 2026-11-24 · retrieval only (no LLM) · shared knowledge base, 2203 chunks
Config: `top_k=5`, candidates per retriever = 20,
RRF k=60, `similarity_threshold=0.77`, BM25 k1=1.5 b=0.75, lexical query mode `any`.
Reproduce: `cd backend; uv run python eval/retrieval_ablation.py`.

Sets: **original** = the 7 questions of `eval/eval.json` (hit = expected file among the top-5);
**short** = 10 keyword queries that must be answered; **off-topic** = the 3 original
refusals + 7 new ones, all must be refused. Gates: **a** = best cosine similarity >=
threshold (today); **b** = a OR a chunk contains ALL non-stop query terms (queries with <= 3 terms);
**c** = like b, but ignoring terms found in more than 10 % of all chunks.

| config | original retrieval hit | short answered | short answered + right file | off-topic refused | vague queries (not counted) |
|---|---|---|---|---|---|
| vector (gate a) | 7/7 | 6/10 | 5/10 | 10/10 | python: refused; python code: refused; example data: answered |
| bm25 (gate b) | 6/7 | 10/10 | 10/10 | 10/10 | python: answered; python code: answered; example data: answered |
| hybrid (gate a) | 7/7 | 6/10 | 6/10 | 10/10 | python: refused; python code: refused; example data: answered |
| hybrid (gate b) | 7/7 | 10/10 | 10/10 | 10/10 | python: answered; python code: answered; example data: answered |
| hybrid (gate c) | 7/7 | 10/10 | 10/10 | 10/10 | python: refused; python code: refused; example data: answered |

Vague queries (`python`, `python code`, `example data`) are made of very common words; whether to
answer them is a judgement call, so they are reported, not counted.

## Decision

Chosen gate: **c** (`retrieval.ANSWER_GATE`), default `RETRIEVAL_MODE=hybrid`.
Acceptance: original retrieval not worse than vector (7/7), off-topic refused 100 %, short-query
answered rate strictly higher than vector-only (10/10 vs 6/10). Gate a keeps today's refusals but
cannot answer short queries (a one-word embedding is weak). Gate b answers them, but also answers
`python` (it is in 17 % of the chunks, so "a chunk contains every term" proves nothing). Gate c
drops terms found in more than 10 % of all chunks from the lexical rule, so it keeps b's gains and
refuses the vague queries. Caveat: 0.1 was picked on this corpus (2203 chunks, 968 of them release
notes); a different corpus may need another value.

## Misses

- `vector (gate a)`: short `CORS` -> tutorial/cors.md, tutorial/cors.md, tutorial/middleware.md
- `vector (gate a)`: short `Depends` -> tutorial/dependencies/index.md, release-notes.md, tutorial/security/get-current-user.md
- `vector (gate a)`: short `response_model` -> release-notes.md, advanced/custom-response.md, tutorial/response-model.md
- `vector (gate a)`: short `middleware` -> tutorial/middleware.md, advanced/middleware.md, advanced/middleware.md
- `hybrid (gate a)`: short `CORS` -> tutorial/cors.md, tutorial/cors.md, tutorial/cors.md
- `hybrid (gate a)`: short `Depends` -> reference/dependencies.md, tutorial/dependencies/index.md, advanced/advanced-dependencies.md
- `hybrid (gate a)`: short `response_model` -> tutorial/response-model.md, advanced/additional-responses.md, release-notes.md
- `hybrid (gate a)`: short `middleware` -> tutorial/middleware.md, advanced/middleware.md, reference/middleware.md
