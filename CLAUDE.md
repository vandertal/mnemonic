# CLAUDE.md — Mnemonic

Read this file first in every session. Then read `docs/ROADMAP.md` to see the current lab and milestone.

## What we are building

**Mnemonic** — an AI study assistant. A user takes a ready knowledge base or uploads their own files,
asks questions (answers cite their sources, or honestly say "I don't know"),
and gets flashcards to remember the material — from text and from images.

Full description: `docs/PRODUCT.md`. Plan and status: `docs/ROADMAP.md`.

This is a university project (42-Lab program, track: 31 → 22 → 21 → 15 → 34 → 42).
Lab briefs live in the teacher's repo next to this one:
`../Programming-Practice-Projects/labs/lab-NN-*.md`. Read the current lab's brief before planning work.

## About the developer (important)

- Solo student. Has ADHD: keep answers short and structured, one task at a time, no walls of text.
- Talk to the developer **in Russian**. Write code, comments, commit messages and docs in **English**.
- Code generation is welcome, BUT the developer must defend every line at the lab defense.
  After each task, give a short "what & why" summary: 3–7 bullets on the key decisions and the concepts to understand.
- Work like a real team: point out skipped steps, missing tests, security issues, bad practices — unless the developer explicitly decides to cut scope.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic, managed with `uv` |
| Database | PostgreSQL + pgvector (Neon in the cloud); SQLAlchemy + Alembic migrations (from lab 21) |
| AI — text | RAG: chunking → embeddings → pgvector search → LLM with citations. LLM provider behind one interface (cloud API or local Ollama) |
| Search | Own positional inverted index + BM25 (stdlib, lab 15), fused with pgvector results (RRF) |
| Frontend | React + TypeScript + Vite (from lab 22) |
| Quality | `ruff` (lint + format), `pytest`, GitHub Actions CI |
| Deploy | Backend: Render. Frontend: static hosting (Vercel/Netlify/Cloudflare Pages) |

Do not add a new dependency or service without asking first and explaining why.

## Repository layout

```
mnemonic/
├─ backend/        # FastAPI app (created in lab 31)
├─ frontend/       # React SPA (created in lab 22)
├─ docs/           # PRODUCT, ROADMAP, SETUP, decisions/, labs/
├─ CLAUDE.md
└─ README.md
```

## Environment

- Windows 11, PowerShell 7 (`pwsh`). Use PowerShell-compatible commands.
- Python only through `uv` (`uv add`, `uv run ...`). Never use bare `pip` or the system Python.
- Secrets only in `.env` (git-ignored). Commit a `.env.example` with empty values instead.

## How we work

1. **One milestone per session.** Start by restating the milestone and a short plan; wait for "ok" before large changes.
2. **Vertical slice first:** the thinnest end-to-end version that works, then improve.
3. **Small commits**, Conventional Commits style: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
   No `Co-Authored-By` or other AI attribution lines in commit messages or PR descriptions.
4. **Tests** for new logic (pytest). Run `ruff` and tests before saying a task is done.
5. **Never** commit secrets, `.env`, model weights or large data files.
6. At the end of a milestone: tick it in `docs/ROADMAP.md`, add notable decisions to `docs/decisions/`.
7. At the end of a lab: help prepare answers to the lab's *Reflection* questions in `docs/labs/lab-NN.md`, then tag: `git tag lab-NN`.

## Commands

Filled in as the project grows.

```powershell
# backend (from lab 31)
cd backend
uv run fastapi dev src/mnemonic/main.py   # http://127.0.0.1:8000
uv run pytest                              # unit tests; integration tests skip themselves
$env:TEST_DATABASE_URL = "postgresql://..."  # a THROWAWAY database: these tests wipe it
uv run pytest -m integration               # real Postgres + pgvector (CI runs them every push)
uv run ruff check . ; uv run ruff format .
uv run alembic upgrade head                # apply migrations (DATABASE_URL)
uv run alembic downgrade -1                # undo the last one
uv run alembic revision -m "what changes"  # new raw-SQL migration

# search engine CLI (lab 15), from backend/
uv run python scripts/search_cli.py                      # interactive; FastAPI docs by default
uv run python scripts/search_cli.py --bench              # index time, size, p50/p95 latency
uv run python scripts/search_cli.py --ranker tfidf --mode any --explain 1 --dir <folder>

# frontend (from lab 22)
cd frontend
npm run dev       # runs the API preflight first
npm run doctor    # only the preflight: is VITE_API_URL reachable and the right API?
npm run test      # vitest
npx tsc -b ; npx oxlint ; npm run build
```
