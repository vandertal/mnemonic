# MANIFESTO

<!-- TODO_STUDENT: rewrite The Question (and anything else) in your own words; this is a draft built from docs/PRODUCT.md and the ADRs. -->

## The Question

Can a student trust an AI that explains their own notes, because every sentence of its answer can be checked against the source?

## The Premise

A student has a pile of material (lecture notes, PDFs, documentation) and too little time. Reading everything takes
too long, and plain search finds words, not answers: it returns a list of places to read, not an explanation.

A generic chatbot does explain, but it invents answers and hides where they came from. For studying that is the worst
combination: a confident wrong sentence is exactly what you will remember. So the useful thing is an assistant that
answers only from the material, shows the passage behind every claim, and says "not in your materials" when it cannot
find one.

Remembering is the other half. Turning material into flashcards by hand is slow, so most people never do it. Mnemonic
puts the three steps in one place: ask, check the cited source, press "Make flashcards".

## The Stack

- **FastAPI + PostgreSQL with pgvector** (Neon): accounts, chat sessions, documents and vector search in one database.
- **RAG with Gemini and local embeddings** (fastembed, `BAAI/bge-small-en-v1.5`): small enough for a 512 MB free instance
  ([ADR 0001](docs/decisions/0001-fastembed-over-sentence-transformers.md)).
- **Our own inverted index with BM25**, fused with the vector results (RRF), so short keyword queries are answered
  ([ADR 0005](docs/decisions/0005-hybrid-retrieval.md)).
- **React + TypeScript SPA** on Cloudflare, and a **Telegram bot** that is a second client of the same backend
  ([ADR 0007](docs/decisions/0007-telegram-client.md)).
- Chosen because every part is free-tier friendly, and each one was a lab of the program (31, 22, 21, 15, 34).

## The Constraints

What Mnemonic will not do ([docs/PRODUCT.md](docs/PRODUCT.md), the ADRs):

- **No mobile app.** The web app and a Telegram bot are the clients.
- **No payments.**
- **No training of our own LLM.** Two pre-trained models (Gemini, bge-small) plus retrieval and guardrails.
- **One ready knowledge base** (the FastAPI documentation), not "all of the internet"; users can add their own files, but
  the Telegram bot only sees the shared one.
- **An English embedder.** The knowledge base and the questions that work best are English.
- **Free-tier limits are accepted, not hidden:** Render sleeps after 15 minutes idle and has 512 MB of memory, and the
  Gemini free tier is rationed by a service-wide limit (`GLOBAL_RPM`).
- **No tracking of what you ask.** Our own events table stores flags only, never the text of a question
  ([ADR 0006](docs/decisions/0006-capstone-metrics.md)).

## The Answer

> 42

Web: https://mnemonic.vlad-slv.workers.dev · Telegram: https://t.me/mnemonicus_bot · API: https://mnemonic-y1js.onrender.com · Code: https://github.com/vandertal/mnemonic

<!-- TODO_STUDENT: sign it (name, date). -->
— Vladislav
