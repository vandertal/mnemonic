# Benchmark: RAG vs plain LLM

- Date: 2026-11-20
- Model (both sides): gemini-3.5-flash-lite
- BASE_URL (RAG side): http://localhost:8000
- Questions: 7 on-topic + 3 off-domain (eval/eval.json)
- Requests with errors: 0

## Summary

| metric | RAG | plain LLM |
|---|---|---|
| Keywords found, on-topic (mean share, 7 q) | 93% | 100% |
| Honest refusal, off-domain (3 q) | 3/3 | 0/3 |
| On-topic answers with source links | 7/7 | 0/7 (none by design) |
| False refusals, on-topic | 0/7 | 0/7 |

## Per question

| # | type | question | RAG keywords | plain keywords | RAG sources | RAG refused | plain refused |
|---|---|---|---|---|---|---|---|
| 1 | on | How do I declare a query parameter with validation? | 100% | 100% | 2 | no | no |
| 2 | on | How do I add OAuth2 password authentication with JWT tokens? | 100% | 100% | 4 | no | no |
| 3 | on | How do I run a background task after returning a response? | 50% | 100% | 1 | no | no |
| 4 | on | How do I enable CORS in FastAPI? | 100% | 100% | 1 | no | no |
| 5 | on | How do I define a request body with a Pydantic model? | 100% | 100% | 2 | no | no |
| 6 | on | How do I upload a file in FastAPI? | 100% | 100% | 3 | no | no |
| 7 | on | How do I return an error response with a custom status code using HTTPException? | 100% | 100% | 2 | no | no |
| 8 | off | How do I write a Django view that renders a template? | - | - | - | yes | no |
| 9 | off | How do I cook a vegetarian lasagna? | - | - | - | yes | no |
| 10 | off | Who won the 2022 FIFA World Cup? | - | - | - | yes | no |

## Limitations

- Only 10 questions: one question moves a metric by 10-14 points. Treat differences as hints.
- The keyword metric checks that expected words appear, not that the answer is correct.
- The plain LLM may know FastAPI from its training data, so on-topic keywords are not a
  fair test of what retrieval adds; the docs here are public and widely seen.
- "Honest refusal" for the plain model is a substring match on a short phrase list: coarse,
  with false negatives and false positives. For off-domain questions a plain assistant
  answering them is normal behaviour; the metric only measures staying in scope.
- "Source links" is 0 for the plain model by construction: it is given no chunks to cite.
- One run per side, no repeats; model output varies between runs.

## Conclusion

- On on-topic questions the plain model is **not worse**: 100% of keywords vs 93% for RAG (the only
  difference is one question where RAG answered from a narrower chunk). On this set the benchmark does **not**
  show that RAG answers FastAPI questions better. The likely reason is that Gemini already knows the public
  FastAPI docs.
- What RAG clearly adds here is *behaviour*, not keyword score: every on-topic answer has source links that
  can be opened and checked (7/7 vs 0/7), and off-domain questions get a refusal (3/3 vs 0/3) instead of an
  answer from outside knowledge. Whether staying in scope is "better" depends on the product: for a study
  tool over a fixed knowledge base, yes.
- RAG should matter more for private or new documents the model has never seen (that is what M7 uploads are
  for); this benchmark cannot test that.
