# Roadmap

Track: **31 → 22 → 21 → 15 → 34 → 42** (Track B + SPA; swaps: 32 → 21 confirmed, 33 → 15 on 2026-11-24 — confirm with the instructor).

Target: **Standard** in every lab, **Advanced** where time allows.
Lab briefs: `../Programming-Practice-Projects/labs/`.

## Cycle for every lab

1. Read the brief → write `docs/labs/lab-NN.md` (requirements + 3–5 milestones).
2. Vertical slice (thinnest end-to-end version).
3. Reach Standard.
4. Advanced side quest (optional).
5. Defense checklist: Reflection answers, README section, deploy works.
6. `git tag lab-NN` and push the tag.

## Status

- [x] 0. Setup — tools, repository, CLAUDE.md, docs
- [x] 31 — LLM RAG App · core: chat over documents with citations (Standard + Advanced; open: 5+ real users, hard billing limit, Ollama deferred)
- [x] 22 — SPA Frontend · chat, documents, flashcards, uk/en, themes; live on Cloudflare; Lighthouse ≥90 (open: Reflection rewrite in own words, 60s recording, Cmd+K skipped)
- [x] 21 — REST API With Auth · accounts, tests, CI/CD; deployed, live smoke 6/6 (open: `git tag lab-21` on main, TODO_LIVE_URL in README, Reflection rewrite)
- [ ] **15 — Mini Search Engine** · own inverted index → hybrid retrieval in the RAG ← **current** (M1 engine ✅, M2 hybrid + API + eval ✅, M3 SPA + close)
- [~] 33 — Object Detection & Tracking · replaced by 15 (plan archived in `docs/labs/lab-33.md`)
- [ ] 34 — AI Capstone · real users, landing, metrics
- [ ] 42 — Life, the Universe, and Everything · MANIFESTO, video, retro

## Current lab

**Lab 15 — M2 done, M3 next (SPA search panel + close).** Plan: [`docs/labs/lab-15.md`](labs/lab-15.md). Task for Claude Code: `docs/prompts/lab15-m2.md` (done).
