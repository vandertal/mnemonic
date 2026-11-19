"""Benchmark: the RAG pipeline vs the same LLM asked the same questions with no retrieval.

Same 10 questions as run_eval.py (eval.json).
  RAG   - through the running server over HTTP, exactly like run_eval.py.
  plain - the backend's provider called directly (an import, NOT a public endpoint): the question
          alone, no system prompt, no context.

Usage (from the repo root; `uv run --project backend` gives the backend's dependencies):
    $env:APP_API_KEY = "..."; $env:BASE_URL = "http://localhost:8000"; $env:GLOBAL_RPM = "5"
    uv run --project backend python eval/run_benchmark.py

Writes eval/benchmark.md. A hand-written "## Conclusion" section in the old file is kept.
Metrics are plain string checks, see the README ("Benchmark") for what they do NOT measure.
"""

import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))  # run_eval.py lives next to this file
import run_eval  # noqa: E402  (its module-level config reads BASE_URL, APP_API_KEY, GLOBAL_RPM)

from mnemonic.config import Settings  # noqa: E402
from mnemonic.llm.factory import build_provider, model_name  # noqa: E402
from mnemonic.llm.retry import stream_with_retry  # noqa: E402
from mnemonic.schemas import Message  # noqa: E402

# A crude list of phrases for "the model declined / said it does not know". Substring match on
# the lower-cased answer: it misses polite refusals worded differently and can fire on a normal
# answer that happens to contain a phrase. Good enough for a sanity check, not a measurement.
REFUSAL_PHRASES = [
    "i don't know",
    "i do not know",
    "i'm not sure",
    "i am not sure",
    "i cannot answer",
    "i can't answer",
    "i cannot help",
    "i can't help",
    "i don't have information",
    "i do not have information",
    "i don't have access",
    "not able to answer",
    "outside the scope",
    "outside of my scope",
    "beyond the scope",
]


def refused(answer: str) -> bool:
    low = answer.lower().replace("’", "'")  # curly apostrophe -> straight
    return any(p in low for p in REFUSAL_PHRASES)


def keyword_share(answer: str, keywords: list[str]) -> float:
    low = answer.lower()
    return sum(k.lower() in low for k in keywords) / len(keywords)


async def plain_answer(provider, question: str) -> tuple[str, str | None]:
    """The question alone, nothing else. Returns (answer, error)."""
    parts: list[str] = []
    try:
        async for token in stream_with_retry(provider, [Message(role="user", content=question)]):
            parts.append(token)
    except Exception as exc:  # report it in the table, do not abort the whole benchmark
        return "".join(parts), f"{type(exc).__name__}: {exc}"
    return "".join(parts), None


def pct(x: float) -> str:
    return f"{x:.0%}"


def main() -> int:
    if not run_eval.API_KEY:
        print("Set APP_API_KEY in the environment.")
        return 1
    items = json.loads((HERE / "eval.json").read_text(encoding="utf-8"))
    # backend/.env explicitly: the repo root is the working directory here, not backend/.
    settings = Settings(_env_file=HERE.parent / "backend" / ".env")
    if settings.llm_provider == "fake":
        print("LLM_PROVIDER is 'fake' in backend/.env: a benchmark against it is meaningless.")
        return 1
    provider = build_provider(settings)
    model = model_name(settings)

    rows = []
    for i, item in enumerate(items, 1):
        q = item["question"]
        off = bool(item.get("expect_idk"))
        print(f"[{i}/{len(items)}] {q}")

        r_answer, r_sources, r_error = run_eval.ask(q)
        r_idk = run_eval.IDK in r_answer.lower()
        if r_error is None and not r_idk:  # only a real LLM call spends the budget
            time.sleep(run_eval.PAUSE)

        p_answer, p_error = asyncio.run(plain_answer(provider, q))
        if i < len(items):
            time.sleep(run_eval.PAUSE)

        rows.append(
            {
                "q": q,
                "off": off,
                "keywords": item.get("keywords", []),
                "rag": {"answer": r_answer, "sources": r_sources, "error": r_error, "idk": r_idk},
                "plain": {"answer": p_answer, "error": p_error, "refused": refused(p_answer)},
            }
        )

    on = [r for r in rows if not r["off"]]
    off = [r for r in rows if r["off"]]
    rag_kw = sum(keyword_share(r["rag"]["answer"], r["keywords"]) for r in on) / len(on)
    plain_kw = sum(keyword_share(r["plain"]["answer"], r["keywords"]) for r in on) / len(on)
    rag_refuse = sum(r["rag"]["idk"] for r in off)
    plain_refuse = sum(r["plain"]["refused"] for r in off)
    rag_cited = sum(bool(r["rag"]["sources"]) for r in on)
    rag_false = sum(r["rag"]["idk"] for r in on)
    plain_false = sum(r["plain"]["refused"] for r in on)
    errors = sum(1 for r in rows if r["rag"]["error"] or r["plain"]["error"])

    summary = "\n".join(
        [
            "| metric | RAG | plain LLM |",
            "|---|---|---|",
            f"| Keywords found, on-topic (mean share, {len(on)} q) | {pct(rag_kw)} | {pct(plain_kw)} |",
            f"| Honest refusal, off-domain ({len(off)} q) | {rag_refuse}/{len(off)} | {plain_refuse}/{len(off)} |",
            f"| On-topic answers with source links | {rag_cited}/{len(on)} | 0/{len(on)} (none by design) |",
            f"| False refusals, on-topic | {rag_false}/{len(on)} | {plain_false}/{len(on)} |",
        ]
    )

    lines = [
        "| # | type | question | RAG keywords | plain keywords | RAG sources | RAG refused | plain refused |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        if r["off"]:
            kw_r = kw_p = src = "-"
        else:
            kw_r = pct(keyword_share(r["rag"]["answer"], r["keywords"]))
            kw_p = pct(keyword_share(r["plain"]["answer"], r["keywords"]))
            src = str(len(r["rag"]["sources"]))
        err = " (error)" if r["rag"]["error"] or r["plain"]["error"] else ""
        lines.append(
            f"| {i} | {'off' if r['off'] else 'on'} | {r['q']}{err} | {kw_r} | {kw_p} | {src} | "
            f"{'yes' if r['rag']['idk'] else 'no'} | {'yes' if r['plain']['refused'] else 'no'} |"
        )
    table = "\n".join(lines)

    previous = HERE / "benchmark.md"
    conclusion = ""
    if previous.exists():
        old = previous.read_text(encoding="utf-8")
        if "\n## Conclusion" in old:
            conclusion = "\n## Conclusion" + old.split("\n## Conclusion", 1)[1]

    text = (
        f"# Benchmark: RAG vs plain LLM\n\n- Date: {date.today().isoformat()}\n"
        f"- Model (both sides): {model}\n- BASE_URL (RAG side): {run_eval.BASE_URL}\n"
        f"- Questions: {len(on)} on-topic + {len(off)} off-domain (eval/eval.json)\n"
        f"- Requests with errors: {errors}\n\n"
        f"## Summary\n\n{summary}\n\n## Per question\n\n{table}\n\n"
        "## Limitations\n\n"
        "- Only 10 questions: one question moves a metric by 10-14 points. Treat differences as hints.\n"
        "- The keyword metric checks that expected words appear, not that the answer is correct.\n"
        "- The plain LLM may know FastAPI from its training data, so on-topic keywords are not a\n"
        "  fair test of what retrieval adds; the docs here are public and widely seen.\n"
        '- "Honest refusal" for the plain model is a substring match on a short phrase list: coarse,\n'
        "  with false negatives and false positives. For off-domain questions a plain assistant\n"
        "  answering them is normal behaviour; the metric only measures staying in scope.\n"
        '- "Source links" is 0 for the plain model by construction: it is given no chunks to cite.\n'
        "- One run per side, no repeats; model output varies between runs.\n"
        f"{conclusion}"
    )
    previous.write_text(text, encoding="utf-8")
    print("\n" + summary + "\n\nWrote eval/benchmark.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
