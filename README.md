# mnemonic
AI study assistant: ask your documents, get flashcards from text and images

**Live demo:** <https://mnemonic-y1js.onrender.com> — the free tier sleeps after 15 minutes idle, the first request takes ~30–60 s.

## Features

- **Questions over the FastAPI docs (RAG).** Answers stream in and cite their sources; an off-topic
  question gets "I don't know" without calling the LLM.
- **Clickable citations.** Click a source under an answer to read the exact chunk text
  (`GET /chunks/{id}`).
- **Conversation memory.** The last 3 question/answer pairs (`HISTORY_MESSAGES=6`) go into the prompt, so
  "and what about X?" works. Retrieval still searches only by the *current* question, so a vague follow-up
  such as "how do I make it optional?" can retrieve poorly.
- **Flashcards.** "Make flashcards" under an answer turns it into 3–5 question/answer cards (click to flip).
  The model returns JSON that is validated against a Pydantic schema (structured output); `POST /flashcards`.
- **Eval and benchmark** against a plain LLM: see below.
- Sessions persist in Postgres, access code + per-IP and global rate limits, every LLM call is logged
  (tokens, cost estimate).

## Access

The service spends a small free-tier LLM quota, so it is closed behind an access code (`X-API-Key`).
Codes are handed out **manually** by the author. The page asks for the code on the first visit and remembers
it in the browser; a wrong code is erased and asked for again. Limits: 10 requests/min per IP and a
service-wide LLM budget (`GLOBAL_RPM`, default 5/min) — over the limit the page shows "try again in N s".

## Run locally

See [backend/README.md](backend/README.md) and [docs/SETUP.md](docs/SETUP.md). Copy `backend/.env.example`
to `backend/.env` and fill it in (never commit `.env`).

## Deploy (Render, free tier)

The service is described in [render.yaml](render.yaml) (a Render Blueprint). Secrets are never in the repo —
Render asks for them in the dashboard.

1. Push the repo to GitHub. Make sure the database is ingested (`uv run python -m mnemonic.ingest` locally).
2. Render dashboard → **New +** → **Blueprint** → pick this repo → **Apply**.
3. Fill in the environment variables when asked (or later: service → **Environment**):

   | Variable | Value |
   |---|---|
   | `LLM_PROVIDER` | `gemini` |
   | `GEMINI_API_KEY` | key from Google AI Studio (server-side only) |
   | `GEMINI_MODEL` | e.g. `gemini-3.5-flash-lite` (empty = default) |
   | `DATABASE_URL` | Neon connection string (`...?sslmode=require`) |
   | `APP_API_KEY` | the access code (the app refuses to start without it) |

   `FASTEMBED_CACHE_PATH` is already set in `render.yaml` (not a secret).
4. Wait for the build, open the `onrender.com` URL, put it in the "Live demo" line above.
5. Check **Logs**: the startup line `LLM provider: gemini (model: ...)` shows what runs live (the key is never logged).

### Memory (free tier = 512 MB)

- Embeddings run **locally on the server** with fastembed (ONNX, no PyTorch), model `BAAI/bge-small-en-v1.5`
  (see [ADR 0001](docs/decisions/0001-fastembed-over-sentence-transformers.md)).
- Measured locally: ~120 MB after importing the app, ~250 MB with the model loaded, peak ~280 MB.
  Check the real number in Render → **Metrics** → Memory after a few questions.
- The model is loaded lazily, on the first question.

### Where the embedding model lives

fastembed caches models in the system temp dir by default (`/tmp/fastembed_cache`), which Render does **not**
keep between deploys/restarts — every cold start would download ~65 MB before the first answer.
So the build command downloads the model into `backend/.cache/fastembed` (the project directory, which is kept
from build to run; the folder is git-ignored) and `FASTEMBED_CACHE_PATH` points there.
Result: no download at runtime, the first question only pays the ~1 s model load.

## Eval

A small regression check of the whole pipeline (retrieval → LLM → citations → "I don't know").

**Method.** [eval/eval.json](eval/eval.json) has 10 questions about the FastAPI docs: 7 on-topic (each with
an `expected_file` and 2 `keywords`, taken from the real chunks) and 3 off-domain (Django, a recipe, sports).
[eval/run_eval.py](eval/run_eval.py) calls the running server over HTTP, a fresh session per question, and
pauses between LLM calls so the service-wide `GLOBAL_RPM` budget is not exceeded (on 429 it waits
`Retry-After` and retries once).

```powershell
$env:APP_API_KEY = "<code>"; $env:BASE_URL = "http://localhost:8000"; $env:GLOBAL_RPM = "5"
python eval/run_eval.py     # standard library only; writes eval/results.md
```

**Metrics** (plain string checks, no LLM judge):

- *Retrieval hit* — `expected_file` is among the `sources` of the answer.
- *Keywords* — share of the expected keywords found in the answer text (case-insensitive).
- *IDK correctness* — an off-domain question gets "I don't know" and an empty `sources`.

**Results** (2026-11-19, local server, real Gemini + Neon, `gemini-3.5-flash-lite`):

| metric | score |
|---|---|
| Retrieval hit | 6/7 |
| Answer keywords | 93% |
| IDK correctness (off-domain) | 3/3 |

The one retrieval miss (background tasks): the model cited `reference/background.md` instead of
`tutorial/background-tasks.md`. Both are relevant, so this is partly a strict-metric artefact.
Full table: [eval/results.md](eval/results.md).

**Honest limitations.**

- Only 10 questions: one question is 10 percentage points, so differences are noise-level. This is a smoke test, not a benchmark.
- No LLM judge: keywords only show that the answer mentions the right terms, not that it is correct.
- `sources` contains only the chunks the model *cited*, so "retrieval hit" mixes retrieval quality and citing behaviour.
- The similarity threshold (0.77) was calibrated on 8 questions; the margin to the nearest off-domain score is ~0.03.
  The off-domain questions here are different from the calibration ones, but still few and easy.
- One run, one model, non-deterministic LLM output: a re-run can differ.

## Benchmark: RAG vs plain LLM

[eval/run_benchmark.py](eval/run_benchmark.py) asks the same 10 questions twice with the same model: through the
running server (RAG) and directly through the backend's provider with no retrieval and no system prompt (plain).

```powershell
$env:APP_API_KEY = "<code>"; $env:BASE_URL = "http://localhost:8000"; $env:GLOBAL_RPM = "5"
uv run --project backend python eval/run_benchmark.py     # writes eval/benchmark.md
```

Results (2026-11-20, `gemini-3.5-flash-lite`, full table in [eval/benchmark.md](eval/benchmark.md)):

| metric | RAG | plain LLM |
|---|---|---|
| Keywords found, on-topic (7 q) | 93% | 100% |
| Honest refusal, off-domain (3 q) | 3/3 | 0/3 |
| On-topic answers with source links | 7/7 | 0/7 (none by design) |
| False refusals, on-topic | 0/7 | 0/7 |

**What it shows and what it does not.** RAG gives checkable sources and stays in scope; it did *not* beat the
plain model on keywords, probably because the model knows the public FastAPI docs from training. So this is
not proof that "RAG is better". Limits: 10 questions, one run, keywords do not measure correctness, and the
plain-model "refusal" is a crude substring match on a short phrase list (it misses refusals worded differently
and can fire on normal answers); for off-domain questions an ordinary assistant answering is not a bug.
