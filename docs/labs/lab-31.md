# Lab 31 — LLM RAG App

Brief: `../Programming-Practice-Projects/labs/lab-31-llm-rag-app.md`
Goal: **Standard**, Advanced side quests where time allows.
Domain: **FastAPI documentation** (see [Make it yours](#3-make-it-yours--why-fastapi-docs)).

## 1. Requirements

Each item shows the milestone that closes it.

### Basic — "It Talks to Your Docs"

- [ ] Web chat UI → **M1**
- [ ] Streamed LLM responses → **M1**
- [ ] RAG over the domain documents → **M2 + M3**
- [ ] Source citations next to answers → **M3**
- [ ] 5+ seed questions give useful, accurate answers → **M3**
- [ ] Deployed to a public URL → **M4**

### Standard — "It's a Real Mini-Product"

- [ ] Session history persists across reloads (Postgres) → **M5**
- [ ] "I don't know" handling when retrieval fails (similarity threshold) → **M3**
- [ ] Eval set: `eval.json` with 10 Q&A pairs + run script, results recorded → **M5**
- [ ] Rate limit (per IP) + API-key gate → **M5**
- [ ] Every LLM call logged (tokens, cost estimate) → **M5**
- [ ] Polished UI, works on mobile → **M5**
- [ ] 5+ real users → **M5**

### Advanced — side quests

- [ ] Production vector DB (pgvector) → **M2**
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
- [ ] Hard billing limit set on the LLM provider → **M1** (before the first call)
- [ ] Rate limit + auth in place (no anonymous unlimited use) → **M5**
- [ ] Streaming works in production → **M4**
- [ ] Mobile UI works → **M5**
- [ ] Citations point to real chunks (cited IDs validated) → **M3**
- [ ] "I don't know" tested with off-domain questions → **M3** (+ eval in **M5**)
- [ ] No secrets in source → **M1** (`.env.example`), re-checked in **M4**
- [ ] README documents the eval methodology and results → **M5**

## 2. Milestones

### M1 — Skeleton

- `backend/` created with `uv init`; FastAPI app.
- `LLMProvider` interface (`stream(messages) -> async iterator of tokens`).
  `GeminiProvider` is the default; the provider is chosen by `LLM_PROVIDER` in `.env`.
- `POST /chat` streams tokens back (streaming response / SSE).
- Plain HTML + JS chat page served by the backend.

**Definition of Done**
- A question typed in the browser → the answer streams in word by word.
- API key only in `.env`; `.env.example` committed with empty values.
- Spend limit set on the Gemini account.
- Tests: provider selection from settings, chat endpoint with a fake provider. `ruff` + `pytest` green.

### M2 — Data

- Ingest script: fetch the FastAPI docs Markdown (git clone into a git-ignored folder — raw data is not committed).
- Chunk into ~500 tokens with ~50 overlap; keep metadata (file path, heading).
- Local embeddings with **fastembed** (ONNX, no PyTorch), model `BAAI/bge-small-en-v1.5` (384 dims).
  See [ADR 0001](../decisions/0001-fastembed-over-sentence-transformers.md).
- Store chunks + vectors in Neon Postgres with pgvector.

**Definition of Done**
- `uv run python -m <package>.ingest` fills the table.
- Re-running ingest is idempotent (no duplicates).
- Tests for the chunker (sizes, overlap, metadata).
- Row count and one sample similarity query documented here.

### M3 — RAG

- Embed the question → top-k (k = 5) cosine search in pgvector.
- Prompt: system message + numbered chunks + question; the model cites chunk IDs.
- Cited IDs are validated against the retrieved ones; invalid citations are dropped.
- Best similarity below the threshold → "I don't know" without calling the LLM.

**Definition of Done**
- 5 seed questions answered correctly with real citations.
- 3 off-domain questions → "I don't know".
- Threshold value and how it was chosen documented here.

### M4 — Deploy

- Render web service; secrets as environment variables; public URL.

**Definition of Done**
- Streaming works on the live URL.
- Memory usage on Render checked (fits the free tier).
- No secrets in the repo or in the page source.
- README has the live URL.

### M5 — Standard

- Sessions and messages stored in Postgres; chat restored after reload.
- API-key header gate + per-IP rate limit.
- Log of every LLM call: tokens in/out, cost estimate.
- `eval/eval.json` (10 Q&A pairs) + `eval/run_eval.py` + recorded results.
- UI polish, mobile layout.

**Definition of Done**
- Reload keeps the conversation.
- Over the limit → HTTP 429; missing/invalid key → HTTP 401.
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
| 2 | Gemini free tier: rate limits; prompts may be used for training. | Spend limit, backoff on 429, never send private data; second provider behind the same interface. |
| 3 | Bad similarity threshold: too high → "I don't know" on valid questions, too low → hallucinations. | Tune on the eval set; log top scores per question. |
| 4 | Render free service sleeps → slow first request during a demo. | Warm it up before the defense; note it in the README. |
| 5 | Scope creep: M6–M7 are large. | Reach Standard (M5) first; Advanced only after M5 is green. |
