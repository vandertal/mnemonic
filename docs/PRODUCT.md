# Mnemonic — Product one-pager

## One sentence

Take a ready knowledge base or upload your own materials, ask questions instead of reading everything,
and get flashcards to remember it — from text and from images.

## Who it is for

Students and self-learners who have a lot of material (lecture notes, PDFs, documentation)
and need to understand and remember it, not just search it.

## The problem

- Reading everything takes too long; plain search finds words, not answers.
- Generic chatbots invent answers and do not show where the answer came from.
- Turning material into flashcards by hand is slow, especially for diagrams and images.

## Main user flow

1. Open the app → pick a ready knowledge base or upload files (PDF / Markdown / images).
2. Ask a question → the answer streams in with clickable citations, or an honest "not in your materials".
3. Press "Make cards" → get text flashcards and quiz questions from the material.
4. (Backlog) Upload a diagram or photo → the system finds labels and makes "hide-and-recall" image cards.
5. Review cards in a clean flashcard screen.

## Features by layer (lab)

| Lab | Feature |
|---|---|
| 31 | RAG chat over documents: citations, streaming, "I don't know", session history, eval set |
| 22 | SPA: chat, documents, flashcard review screen |
| 21 | Accounts (JWT), per-user documents, rate limits, tests, CI/CD |
| 15 | Hybrid search: own BM25 inverted index + vectors (RRF), search endpoint and panel, "why this result" |
| 34 | Real users: landing page, < 60 s onboarding, one tracked metric, user-feedback write-up |
| 42 | MANIFESTO, demo video, retrospective |

## Non-goals (constraints)

- No mobile app.
- No payments.
- No training of our own LLM.
- One ready knowledge base at first (the FastAPI documentation), not "all of the internet".

## Decided

- Ready knowledge base: **FastAPI documentation** (Markdown, MIT license) — reasons in `docs/labs/lab-31.md`.
- Default LLM: **Gemini free tier**. The provider is switched via `.env` (`LLM_PROVIDER`);
  local Ollama and a paid cloud API are options behind the same interface.

## Open questions

None right now.

## Backlog (after the course)

- Image cards (region detection on diagrams; Gemini vision is the cheap route, YOLO/ONNX the heavy one). Lab 33 plan archived.
- Telegram bot as a second client of the same API.
