# Lab 42 — Life, the Universe, and Everything: Mnemonic

Brief: `../Programming-Practice-Projects/labs/lab-42-life-the-universe-and-everything.md`. **Path A (Synthesis):**
31 (RAG) + 22 (SPA) + 21 (accounts, API) + 15 (own search engine) + 34 (capstone, Telegram bot).

Prepared by an AI assistant from the repo. This file holds facts and pointers only; the Reflection answers must be said
by the student in their own words.

## Submission checklist

| Item | Status | Notes |
|---|---|---|
| `MANIFESTO.md` present, signed, `42` as The Answer | **needs human** | Draft written ([MANIFESTO.md](../../MANIFESTO.md)). Rewrite The Question in your own words, sign it, paste the live URLs. |
| Product shipped (public URL / release) | **needs human** | API is live (`https://mnemonic-y1js.onrender.com`). The SPA URL and the Telegram bot link are not recorded in the repo (`TODO_STUDENT` in README). |
| Demo video (60-120 s) embedded in README | **needs human** | Placeholder in README "Demo". |
| README: hero, quickstart, architecture, Don't Panic | done | Hero image: `docs/screenshots/` is empty: **needs human** (landing / chat screenshots). |
| `docs/RETRO.md` present and specific | done (draft) | Personal parts marked `TODO_STUDENT`. |
| At least one real human (not you) used it; note who | **needs human** | No real-user evidence in the repo (lab 34 M3 is open). |
| At least one prior lab meaningfully reused | done | Labs 31, 22, 21, 15, 34; table in README "Which lab gave what". |
| License chosen | done | MIT, 2026, Vladislav ([LICENSE](../../LICENSE), already in the repo). |
| Public showcase post (optional) | **needs human** | Not written. |
| Honest limitations section | done | README "Honest limitations", "Telegram bot" and "Search" limitations; known issues added in lab 42 M1. |
| `CONTRIBUTING.md` (side quest) | done | [CONTRIBUTING.md](../../CONTRIBUTING.md), linked from README. |
| Defense session (5 minutes) | **needs human** | Fact sheet below. |

## Defense questions: fact sheet

**1. State The Question.**
The draft question is in [MANIFESTO.md](../../MANIFESTO.md): trusting an AI that explains your notes because every answer can be checked against the source.
The product's one-line version: "Ask your notes. Get cited answers. Remember them." ([PRODUCT.md](../PRODUCT.md)).

**2. State The Answer (demo).**
Flow to show: landing → "Try it" → register → one of 3 example questions → streamed answer with citation chips → open a citation (exact chunk, `GET /chunks/{id}`) → "Make flashcards"; then an off-topic question for the honest "not in your materials"; then the Telegram bot.
Fallback if the API is asleep: wake it first (cold start up to a minute, README "Don't Panic").

**3. One architectural decision and its trade-off.**
- Hybrid retrieval ([ADR 0005](../decisions/0005-hybrid-retrieval.md)): own BM25 index fused with pgvector by RRF (k = 60). Gain: short keyword queries answered 10/10 (vector only 6/10), off-topic still refused 10/10. Cost: the index lives in memory of one process (about 27 MB for 2203 chunks, rebuilt in about 2.5 s on every restart); several workers would each keep a copy.
- Alternatives with their own trade-offs: fastembed instead of PyTorch to fit 512 MB ([ADR 0001](../decisions/0001-fastembed-over-sentence-transformers.md)); the Telegram webhook inside the same service instead of a worker ([ADR 0007](../decisions/0007-telegram-client.md)); own events table instead of third-party analytics ([ADR 0006](../decisions/0006-capstone-metrics.md)).

**4. A technical risk that did not pay off.**
- Short-query "I don't know" in lab 31: a query prefix and adding the previous question were both measured and gave no clean on-topic / off-topic gap ("What is the cli?" 0.721 vs "Flask" 0.719); the threshold stayed 0.77 and the weakness was documented ([lab-31.md](lab-31.md), questions 4 and 8). It was fixed later by the lexical gate in lab 15.
- Open at the time of writing: Telegram `/cards` fails in a real chat and an out-of-memory restart on free Render ([lab-34-failures.md](lab-34-failures.md), rows 32-33).

**5. Which prior lab gave the unlock.**
Facts only: lab 15 turned the vector-only chat into hybrid retrieval and fixed the short-query refusals; lab 21's accounts and ownership made real users possible; lab 31 is the core. Which one "clicked" is the student's answer: `TODO_STUDENT`.

**6. What I would cut from the program.**
No repo fact applies: `TODO_STUDENT`. (Repo-visible: lab 33 was replaced by lab 15 in this track, plan archived in [lab-33.md](lab-33.md).)

**7. What is next.**
Open items in [ROADMAP.md](../ROADMAP.md) and [lab-34.md](lab-34.md): real users (M3), billing limit at the AI provider, Render memory numbers, the `/cards` bug. Backlog in [PRODUCT.md](../PRODUCT.md): image cards (from text and images was the original idea; image cards were not built). Whether to maintain it: `TODO_STUDENT`.

## Student to-do (all `TODO_STUDENT` markers)

`grep -rn TODO_STUDENT README.md MANIFESTO.md docs/RETRO.md docs/labs/lab-42.md`
