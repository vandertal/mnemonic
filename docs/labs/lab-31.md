# Lab 31 — LLM RAG App

Brief: `../Programming-Practice-Projects/labs/lab-31-llm-rag-app.md`
Goal: **Standard**, Advanced side quests where time allows.
Domain: **FastAPI documentation** (see [Make it yours](#3-make-it-yours--why-fastapi-docs)).

## 1. Requirements

Each item shows the milestone that closes it.

### Basic — "It Talks to Your Docs"

- [x] Web chat UI → **M1**
- [x] Streamed LLM responses → **M1**
- [x] RAG over the domain documents → **M2 + M3**
- [ ] Source citations next to answers → **M3**
- [x] 5+ seed questions give useful, accurate answers → **M3**
- [ ] Deployed to a public URL → **M4**

### Standard — "It's a Real Mini-Product"

- [ ] Session history persists across reloads (Postgres) → **M5**
- [x] "I don't know" handling when retrieval fails (similarity threshold) → **M3**
- [ ] Eval set: `eval.json` with 10 Q&A pairs + run script, results recorded → **M5**
- [ ] Rate limit (per IP) + API-key gate → **M5**
- [ ] Every LLM call logged (tokens, cost estimate) → **M5**
- [ ] Polished UI, works on mobile → **M5**
- [ ] 5+ real users → **M5**

### Advanced — side quests

- [x] Production vector DB (pgvector) → **M2**
- [ ] Structured output (flashcards as JSON) → **M6**
- [ ] Benchmark: RAG vs plain LLM on the eval set → **M6**
- [ ] Citation UI (click a citation → see the source paragraph) → **M6**
- [ ] Conversational memory (earlier turns, not only retrieval) → **M6**
- [ ] Multi-document upload (per-user document spaces) → **M7**
- [ ] Tool use / agentic loop → **M7**
- [ ] Local model via Ollama + tradeoffs write-up → **M7**

Out of scope for this lab: fine-tuning, voice interface, multi-modal (images come in lab 33).

### Deployment checklist

- [ ] Live URL works → **M4**
- [ ] LLM API key is server-side only, never in the browser → **M1** (design), **M4** (verified)
- [ ] Hard billing limit on the LLM provider: billing not connected (free tier) → **M1**
- [ ] Rate limit + auth in place (no anonymous unlimited use) → **M5**
- [ ] Streaming works in production → **M4**
- [ ] Mobile UI works → **M5**
- [x] Citations point to real chunks (cited IDs validated) → **M3**
- [x] "I don't know" tested with off-domain questions → **M3** (+ eval in **M5**)
- [ ] No secrets in source → **M1** (`.env.example`), re-checked in **M4**
- [ ] README documents the eval methodology and results → **M5**

## 2. Milestones

### M1 — Skeleton ✅ done

- `backend/` created with `uv init`; FastAPI app.
- `LLMProvider` interface (`stream(messages) -> async iterator of tokens`).
  `GeminiProvider` is the default; the provider is chosen by `LLM_PROVIDER` in `.env`.
- `POST /chat` streams tokens back (streaming response / SSE).
- Plain HTML + JS chat page served by the backend.

**Definition of Done**
- [x] A question typed in the browser → the answer streams in word by word.
- [x] API key only in `.env`; `.env.example` committed with empty values.
- [x] Billing is not connected to the Gemini account (free tier) — no way to be charged.
- [x] Tests: provider selection from settings, chat endpoint with a fake provider. `ruff` + `pytest` green.

Notes: a stalled provider times out after `LLM_TIMEOUT_SECONDS`. The default model is
`gemini-3.5-flash-lite`, see [ADR 0002](../decisions/0002-gemini-model-choice.md).

### M2 — Data ✅ done

- Ingest script: fetch the FastAPI docs Markdown (git clone into a git-ignored folder — raw data is not committed).
- Chunk into ~500 tokens with ~50 overlap; keep metadata (file path, heading).
- Local embeddings with **fastembed** (ONNX, no PyTorch), model `BAAI/bge-small-en-v1.5` (384 dims).
  See [ADR 0001](../decisions/0001-fastembed-over-sentence-transformers.md).
- Store chunks + vectors in Neon Postgres with pgvector.

**Definition of Done**
- [x] `uv run python -m mnemonic.ingest` fills the table.
- [x] Re-running ingest is idempotent (no duplicates).
- [x] Tests for the chunker (sizes, overlap, metadata).
- [x] Row count and one sample similarity query documented here.

**Results**

- Source: `docs/en/docs` of the FastAPI repo (shallow clone into `backend/data/`, git-ignored).
- 2203 chunks produced, **2202 rows** stored (one exact duplicate inside a file collapsed by `content_hash`).
- Second run: `Inserted 0. Total rows: 2202`.
- Sample query (cosine, top-3) — "How do I declare a query parameter with validation?":

| similarity | file | heading |
|---|---|---|
| 0.840 | tutorial/path-params-numeric-validations.md | Path Parameters and Numeric Validations > Declare metadata |
| 0.834 | tutorial/query-params-str-validations.md | Query Parameters and String Validations > Alias parameters |
| 0.830 | tutorial/path-params-numeric-validations.md | Path Parameters and Numeric Validations > Recap |

- Decisions: [ADR 0003](../decisions/0003-chunk-identity-and-index.md). Note for M3: top scores for an on-topic
  question are only ~0.83-0.84, so the "I don't know" threshold must be tuned on real data, not guessed.

### M3 — RAG ✅ done

- Embed the question → top-k (k = 5) cosine search in pgvector.
- Prompt: system message + numbered chunks + question; the model cites chunk IDs.
- Cited IDs are validated against the retrieved ones; invalid citations are dropped.
- Best similarity below the threshold → "I don't know" without calling the LLM.
- `/chat` request: the client sends only `user` / `assistant` messages; the server adds the
  `system` message itself (the client must not be able to set or override the system prompt).

**Definition of Done**
- [x] A request with a client-supplied `system` message is rejected (422) — covered by a test.
- [x] 5 seed questions answered with real citations (see caveats below).
- [x] 3 off-domain questions → "I don't know" (no LLM call).
- [x] Threshold value and how it was chosen documented here.

**Results**

- Config: `RETRIEVAL_TOP_K=5`, `SIMILARITY_THRESHOLD=0.77` (default in `config.py`, override in `.env`).
- Cited ids are parsed from the answer (`[42]`, `[42, 43]`) and checked against the retrieved ids; only real
  ones are sent to the client in a `sources` SSE event. Text already streamed is not rewritten, so a
  hallucinated `[999]` may still appear in the text but never in `sources`.
- Rejected input: `system` role (422), a conversation whose last message is not from the user (422).

Threshold — top-1 similarity measured with `backend/scripts/measure_threshold.py`:

| group | question | top-1 |
|---|---|---|
| on | declare a query parameter with validation | 0.840 |
| on | OAuth2 password auth with JWT | 0.808 |
| on | run a background task after a response | 0.855 |
| on | enable CORS | 0.819 |
| on | request body with a Pydantic model | 0.835 |
| off | Django model + migrations | 0.739 |
| off | carbonara recipe | 0.594 |
| off | 2018 World Cup winner | 0.536 |

On-topic min 0.808, off-topic max 0.739 → threshold **0.77**, the middle of the gap. The hardest negative is
"Django" (same domain: Python web framework), so it sets the lower bound. Caveats: only 8 questions, and the
margin is thin (~0.03 on each side); real tuning needs the M5 eval set. Scores of different questions are
not calibrated probabilities — the threshold is an empirical cut for this model and this corpus.

Live run (real Gemini + Neon, 5 on-topic + 3 off-domain):

- CORS, background tasks, request body, OAuth2/JWT: correct answers, citations point to the right files
  (`tutorial/cors.md`, `tutorial/background-tasks.md`, `tutorial/body.md`, `tutorial/security/oauth2-jwt.md`).
- Query validation: cited the right file, but the second code example in the answer is wrong
  (`= None` shown as "required"). Retrieval is fine, the model mixed up two chunks.
- Request body: top-1 for the same question in the measuring script was `security/get-current-user.md`, not
  `body.md` — retrieval noise, but the answer was still grounded (it cited `body.md` from the top-5).
- Off-domain (Django, carbonara, World Cup): "I don't know", provider not called.
- Not done in the UI: the page does not yet render the `sources` event (citations are only in the stream).

### M4 — Deploy

- Render web service; secrets as environment variables; public URL.
- Log the active LLM provider and model at startup (never the key).

Prepared (not closed until the service is live):

- `render.yaml` Blueprint (root `backend`, free plan, uv build, uvicorn on `$PORT`); secrets are `sync: false`.
- Startup log `LLM provider: gemini (model: ...)` added (it was not in M1). `logging.basicConfig(INFO)` too:
  before, our `logger.info` lines were silently dropped under uvicorn.
- Embedding model is downloaded at build time into `backend/.cache/fastembed` (`FASTEMBED_CACHE_PATH`),
  because the default `/tmp` cache is lost on restart. Model size: ~65 MB.
- Memory measured locally: ~250 MB with the model loaded, peak ~280 MB. Still to confirm in Render Metrics.
- Secret scan (tracked files, git history, served page): clean.

**Definition of Done**
- The startup log shows which provider and model the live service uses.
- Streaming works on the live URL.
- Memory usage on Render checked (fits the free tier).
- No secrets in the repo or in the page source.
- README has the live URL.

### M5 — Standard

- Sessions and messages stored in Postgres; chat restored after reload.
- API-key header gate + per-IP rate limit.
- Log of every LLM call: tokens in/out, cost estimate.
- Retry with exponential backoff on 503 (and 429), only **before the first token** has been sent —
  after streaming started a retry would duplicate text.
- A service-wide request budget (see risk 6), not only the per-IP limit.
- `eval/eval.json` (10 Q&A pairs) + `eval/run_eval.py` + recorded results.
- UI polish, mobile layout.

**Definition of Done**
- Reload keeps the conversation.
- Over the limit → HTTP 429; missing/invalid key → HTTP 401.
- A simulated 503 before the first token is retried; a failure after the first token is not (tests with a fake provider).
- Eval score and methodology in the README.
- 5+ real users tried it; short notes on their feedback in this file.

### M6 — Advanced, part 1

- Flashcards via structured output (Pydantic schema → JSON → rendered cards).
- Benchmark: RAG vs plain LLM on the eval set, results table.
- Clickable citations that show the source paragraph.
- Conversation memory: the last N turns go into the prompt.

**Definition of Done**
- Each feature demoed; benchmark numbers in the README.

### M7 — Advanced, part 2

- Upload own documents (Markdown / PDF), stored per user.
- One tool via function calling (e.g. calculator or "search the docs").
- `OllamaProvider` as a local provider + a short tradeoffs note (quality, latency, cost).

**Definition of Done**
- Each feature demoed; switching the provider is one line in `.env`.

## 3. Make it yours — why FastAPI docs

- **Right size and format:** real Markdown, a few hundred pages, MIT-licensed — free to use and redistribute.
- **Answers are verifiable:** this project is built with FastAPI, so I can judge if an answer is correct.
- **Clear off-domain tests:** questions about Django or cooking should get "I don't know" — easy to show at the defense.
- **Fits the product:** it becomes Mnemonic's first ready knowledge base; flashcards from docs help people learn a framework.

## 4. Reflection

Answers are filled in at the end of the lab.

1. **Live demo:** the panel asks 5 questions; how does the model handle each?
   _Answer: TBD_
2. **Walk through the pipeline** for one question — input, embedding, retrieval, prompt, LLM call, streaming, render.
   _Answer: TBD_
3. **Show your eval results.** What's the score? Why is RAG better than a plain LLM?
   _Answer: TBD_
4. **What happens when the user asks an off-domain question?**
   _Answer: TBD_
5. **What does it cost** to answer one question? In tokens, and in dollars?
   _Answer: TBD_
6. **What would you change** to scale to 1000 users? 1 million?
   _Answer: TBD_
7. **What's the difference** between embeddings, fine-tuning, and prompt engineering? When do you use which?
   _Answer: TBD_
8. **What was the hardest part** — chunking, retrieval, hallucinations, UI streaming, or eval?
   _Answer: TBD_

## 5. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | Render free tier has 512 MB RAM; the question is embedded on the server at runtime. PyTorch-based models may not fit. | fastembed (ONNX) instead of sentence-transformers; measure memory in M4. |
| 2 | Gemini free tier: rate limits; prompts may be used for training. | No billing attached (free tier), backoff on 429, never send private data; second provider behind the same interface. |
| 3 | Bad similarity threshold: too high → "I don't know" on valid questions, too low → hallucinations. | Tune on the eval set; log top scores per question. |
| 4 | Render free service sleeps → slow first request during a demo. | Warm it up before the defense; note it in the README. |
| 5 | Scope creep: M6–M7 are large. | Reach Standard (M5) first; Advanced only after M5 is green. |
| 6 | The free-tier Gemini quota is about 5–10 requests per minute for the **whole project**, not per user (figure from the review; verify in AI Studio). A per-IP limit does not protect it: a few users at once (the 5+ real users in M5, the live demo) can exhaust it. | By M5: a global limiter / short queue in front of the LLM, a clear "busy, try again" message instead of a hang, backoff before the first token, no eval runs during a demo. |
