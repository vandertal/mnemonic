"""Retrieval-only ablation: vector vs BM25 vs hybrid, with the candidate "I don't know" gates.

No LLM calls. Runs on the DATABASE_URL database (the dev branch) with the real embedder, over the
shared knowledge base only (no owner), and writes docs/labs/lab-15-eval.md.

    cd backend
    uv run python eval/retrieval_ablation.py

Gates (see mnemonic.retrieval): a = vector similarity >= threshold (today's rule);
b = a OR a chunk has ALL non-stop query terms (<= 3 terms); c = like b, but ignoring terms that
occur in more than 10 % of all chunks.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

from mnemonic.config import get_settings
from mnemonic.retrieval import ANSWER_GATE, GATES, HybridRetriever, PgSource
from mnemonic.search_service import SearchService
from mnemonic.store import PgStore

ROOT = Path(__file__).resolve().parents[2]
EVAL_JSON = ROOT / "eval" / "eval.json"
REPORT = ROOT / "docs" / "labs" / "lab-15-eval.md"

# (query, substrings of acceptable file paths). "must be answered" short / keyword queries.
SHORT = [
    ("CORS", ["tutorial/cors.md"]),
    ("Depends", ["tutorial/dependencies/"]),
    ("response_model", ["tutorial/response-model.md"]),
    ("OAuth2", ["security/"]),
    ("BackgroundTasks", ["tutorial/background-tasks.md"]),
    ("middleware", ["middleware.md"]),
    ("Pydantic", ["body", "pydantic", "response-model", "extra-models"]),
    ("WebSocket", ["websockets.md"]),
    ("HTTPException", ["handling-errors.md"]),
    ("UploadFile", ["request-files.md", "uploadfile.md"]),
]
# must be refused
OFF_TOPIC = [
    "weather tomorrow",
    "pizza recipe",
    "world cup winner",
    "bitcoin price today",
    "how to learn guitar",
    "capital of France",
    "best football player",
]
# Vague queries made of very common words: reported, not counted (is "python" a question?).
JUDGEMENT = ["python", "python code", "example data"]

# (label, retrieval mode, gate)
CONFIGS = [
    ("vector (gate a)", "vector", "a"),
    ("bm25 (gate b)", "bm25", "b"),
    ("hybrid (gate a)", "hybrid", "a"),
    ("hybrid (gate b)", "hybrid", "b"),
    ("hybrid (gate c)", "hybrid", "c"),
]


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set (backend/.env)")
        return 2
    threshold = settings.similarity_threshold
    service = SearchService()
    started = time.perf_counter()
    stats = service.build(PgStore(settings.database_url).index_rows())
    print(
        f"index: {stats.chunks} chunks, {stats.terms} terms, {stats.build_seconds:.2f}s, "
        f"{stats.memory_mb} MB ({stats.memory_source}); total {time.perf_counter() - started:.1f}s"
    )
    source = PgSource(settings.database_url)
    cases = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    original = [c for c in cases if "expected_file" in c]
    original_idk = [c["question"] for c in cases if c.get("expect_idk")]
    refused_set = original_idk + OFF_TOPIC

    rows, details = [], []
    for label, mode, gate_name in CONFIGS:
        retriever = HybridRetriever(
            source, settings.retrieval_top_k, mode, service, settings.retrieval_candidates
        )
        gate = GATES[gate_name]

        def run(question: str, retriever=retriever):
            return retriever(question, None)

        hit = 0
        for c in original:
            hit += any(h.file_path == c["expected_file"] for h in run(c["question"]))
        answered = right = 0
        for q, files in SHORT:
            hits = run(q)
            ok = gate(hits, threshold)
            answered += ok
            good = any(any(f in h.file_path for f in files) for h in hits)
            right += ok and good
            details.append((label, "short", q, ok, [h.file_path for h in hits[:3]]))
        refused = 0
        for q in refused_set:
            hits = run(q)
            ok = not gate(hits, threshold)
            refused += ok
            if not ok:
                details.append(
                    (label, "off-topic ANSWERED", q, False, [h.file_path for h in hits[:3]])
                )
        py = "; ".join(
            f"{q}: {'answered' if gate(run(q), threshold) else 'refused'}" for q in JUDGEMENT
        )
        rows.append(
            (
                label,
                f"{hit}/{len(original)}",
                f"{answered}/{len(SHORT)}",
                f"{right}/{len(SHORT)}",
                f"{refused}/{len(refused_set)}",
                py,
            )
        )

    header = (
        "| config | original retrieval hit | short answered | short answered + right file "
        "| off-topic refused | vague queries (not counted) |"
    )
    table = "\n".join(
        [header, "|---|---|---|---|---|---|"] + ["| " + " | ".join(r) + " |" for r in rows]
    )
    print("\n" + table)
    print("\nMisses:")
    for label, kind, q, ok, files in details:
        if kind != "short" or not ok:
            print(f"  [{label}] {kind}: {q!r} -> {files}")

    misses = "\n".join(
        f"- `{label}`: {kind} `{q}` -> {', '.join(files) or 'no hits'}"
        for label, kind, q, ok, files in details
        if kind != "short" or not ok
    )
    REPORT.write_text(
        f"""# Lab 15 — retrieval ablation

Date: {date.today().isoformat()} · retrieval only (no LLM) · shared knowledge base,
{stats.chunks} chunks.
Config: `top_k={settings.retrieval_top_k}`, candidates per retriever =
{settings.retrieval_candidates}, RRF k=60, `similarity_threshold={threshold}`,
BM25 k1=1.5 b=0.75, lexical query mode `any`.
Reproduce: `cd backend; uv run python eval/retrieval_ablation.py`.

Sets: **original** = the 7 questions of `eval/eval.json` (hit = expected file among the top-5);
**short** = {len(SHORT)} keyword queries that must be answered; **off-topic** = the 3 original
refusals + {len(OFF_TOPIC)} new ones, all must be refused. Gates: **a** = best cosine similarity >=
threshold (today); **b** = a OR a chunk contains ALL non-stop query terms (queries with <= 3 terms);
**c** = like b, but ignoring terms found in more than 10 % of all chunks.

{table}

Vague queries (`python`, `python code`, `example data`) are made of very common words; whether to
answer them is a judgement call, so they are reported, not counted.

## Decision

Chosen gate: **{ANSWER_GATE}** (`retrieval.ANSWER_GATE`), default `RETRIEVAL_MODE=hybrid`.
Acceptance: original retrieval not worse than vector (7/7), off-topic refused 100 %, short-query
answered rate strictly higher than vector-only (10/10 vs 6/10). Gate a keeps today's refusals but
cannot answer short queries (a one-word embedding is weak). Gate b answers them, but also answers
`python` (it is in 17 % of the chunks, so "a chunk contains every term" proves nothing). Gate c
drops terms found in more than 10 % of all chunks from the lexical rule, so it keeps b's gains and
refuses the vague queries. Caveat: 0.1 was picked on this corpus (2203 chunks, 968 of them release
notes); a different corpus may need another value.

## Misses

{misses or "none"}
""",
        encoding="utf-8",
    )
    print(f"\nsaved {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
