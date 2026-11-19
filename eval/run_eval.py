"""Run the eval set against a running Mnemonic server over HTTP. No LLM judge, only string checks.

Usage (from the repo root):
    $env:APP_API_KEY = "..."; $env:BASE_URL = "http://localhost:8000"; $env:GEMINI_MODEL = "..."
    python eval/run_eval.py            # stdlib only, no extra dependencies

Metrics:
  retrieval hit  - expected_file is among the `sources` the server returned (the CITED chunks,
                   not all retrieved ones, so this measures retrieval AND citing together)
  keywords       - share of the expected keywords found in the answer (case-insensitive)
  IDK correct    - off-domain question: the answer says "I don't know" AND `sources` is empty
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("APP_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite (default)"
GLOBAL_RPM = int(
    os.environ.get("GLOBAL_RPM") or 5
)  # must match the server's GLOBAL_RPM
PAUSE = 60 / GLOBAL_RPM + 1  # one LLM call per budget slot, +1 s safety margin
DEFAULT_RETRY_AFTER = 15
IDK = "i don't know"


def parse_sse(stream) -> tuple[str, list[dict], str | None]:
    """Read an SSE stream -> (answer text, sources, error). Same format the web page parses."""
    answer, sources, error = [], [], None
    event, data = "message", None
    for raw in stream:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line == "":  # a blank line ends the block: dispatch it
            if data is not None:
                if event == "message":
                    answer.append(data)
                elif event == "sources":
                    sources = data
                elif event == "error":
                    error = data
            event, data = "message", None
        elif line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
    return "".join(answer), sources, error


def ask(question: str) -> tuple[str, list[dict], str | None]:
    """One question in a fresh session. On 429: wait Retry-After and retry once."""
    body = json.dumps({"session_id": str(uuid.uuid4()), "message": question}).encode()
    for attempt in (1, 2):
        req = urllib.request.Request(
            f"{BASE_URL}/chat",
            data=body,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return parse_sse(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                wait = int(e.headers.get("Retry-After") or DEFAULT_RETRY_AFTER)
                print(f"    429, waiting {wait}s and retrying once")
                time.sleep(wait + 1)
                continue
            return "", [], f"HTTP {e.code}"
        except OSError as e:  # connection refused, timeout, ...
            return "", [], f"network error: {e}"
    return "", [], "unreachable"


def main() -> int:
    if not API_KEY:
        print("Set APP_API_KEY in the environment.")
        return 1
    items = json.loads((HERE / "eval.json").read_text(encoding="utf-8"))
    rows = []
    for i, item in enumerate(items, 1):
        q = item["question"]
        print(f"[{i}/{len(items)}] {q}")
        answer, sources, error = ask(q)
        files = [s["file_path"] for s in sources]
        said_idk = IDK in answer.lower()
        row = {"question": q, "error": error, "files": files}
        if item.get("expect_idk"):
            row["kind"] = "off"
            row["idk_ok"] = error is None and said_idk and not sources
        else:
            row["kind"] = "on"
            row["expected_file"] = item["expected_file"]
            row["hit"] = item["expected_file"] in files
            kws = item["keywords"]
            row["kw_share"] = sum(k.lower() in answer.lower() for k in kws) / len(kws)
            row["false_idk"] = said_idk
        rows.append(row)
        # Only answers that really called the LLM used the service-wide budget.
        if error is None and not said_idk and i < len(items):
            time.sleep(PAUSE)

    on = [r for r in rows if r["kind"] == "on"]
    off = [r for r in rows if r["kind"] == "off"]
    hits = sum(r["hit"] for r in on)
    kw = sum(r["kw_share"] for r in on) / len(on)
    idk = sum(r["idk_ok"] for r in off)
    errors = sum(1 for r in rows if r["error"])

    lines = [
        "| # | type | question | retrieval hit | keywords | IDK ok | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        on_row = r["kind"] == "on"
        note = r["error"] or ("false IDK" if r.get("false_idk") else "")
        hit = ("yes" if r["hit"] else "no") if on_row else "-"
        kws = f"{r['kw_share']:.0%}" if on_row else "-"
        ok = "-" if on_row else ("yes" if r["idk_ok"] else "no")
        lines.append(
            f"| {i} | {r['kind']} | {r['question']} | {hit} | {kws} | {ok} | {note} |"
        )
    table = "\n".join(lines)
    summary = (
        f"- Retrieval hit: **{hits}/{len(on)}**\n"
        f"- Answer keywords: **{kw:.0%}** (mean share found)\n"
        f"- IDK correctness (off-domain): **{idk}/{len(off)}**\n"
        f"- Requests with errors: {errors}"
    )
    print("\n" + table + "\n\n" + summary)

    misses = "\n".join(
        f"- Q{i}: expected `{r['expected_file']}`, cited: {r['files'] or 'nothing'}"
        for i, r in enumerate(rows, 1)
        if r["kind"] == "on" and not r["hit"]
    )
    (HERE / "results.md").write_text(
        f"# Eval results\n\n- Date: {date.today().isoformat()}\n- BASE_URL: {BASE_URL}\n"
        f"- Model: {MODEL}\n- Questions: {len(on)} on-topic + {len(off)} off-domain\n\n"
        f"{summary}\n\n{table}\n"
        + (f"\nRetrieval misses:\n{misses}\n" if misses else ""),
        encoding="utf-8",
    )
    print("\nWrote eval/results.md")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
