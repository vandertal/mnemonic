# mnemonic
AI study assistant: ask your documents, get flashcards from text and images

**Live demo:** <LIVE_URL_PLACEHOLDER> — the free tier sleeps after 15 minutes idle, the first request takes ~30–60 s.

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
