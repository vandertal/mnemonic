"""Interactive search over a folder of text files, plus a benchmark.

    uv run python scripts/search_cli.py                  # FastAPI docs, interactive
    uv run python scripts/search_cli.py --bench
    uv run python scripts/search_cli.py --dir notes --ranker tfidf --mode any --explain 1

Query syntax: foo bar (all terms) | "exact phrase" | -word (exclude).
"""

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

from mnemonic.search import Hit, SearchEngine, Snippet

BACKEND = Path(__file__).resolve().parent.parent
DEFAULT_DIR = BACKEND / "data" / "fastapi" / "docs" / "en" / "docs"  # same as mnemonic.ingest
EXTENSIONS = {".md", ".txt", ".rst"}

BENCH_QUERIES = [
    "Depends",
    "CORS",
    "middleware",
    "OAuth2PasswordBearer",
    "response_model",
    "HTTPException",
    "BackgroundTasks",
    "websocket",
    "pydantic",
    "dependency injection",
    "path parameters",
    "query parameters validation",
    "request body",
    "file upload",
    "security scopes",
    "async await",
    "background tasks",
    '"dependency injection"',
    '"response model"',
    "cors -middleware",
]


def load_corpus(folder: Path) -> tuple[dict[str, str], int, int]:
    """Return ({doc_id: text}, empty_files_skipped, non_utf8_files)."""
    docs: dict[str, str] = {}
    empty = bad_encoding = 0
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXTENSIONS):
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            bad_encoding += 1
        if not text.strip():
            empty += 1
            continue
        docs[path.relative_to(folder).as_posix()] = text
    return docs, empty, bad_encoding


def mark(snippet: Snippet) -> str:
    """Render highlights as ** marks (terminal only; the API never returns HTML)."""
    out, last = [], 0
    for start, end in snippet.highlights:
        out += [snippet.text[last:start], "**", snippet.text[start:end], "**"]
        last = end
    out.append(snippet.text[last:])
    return "".join(out).replace("\n", " ")


def print_hits(hits: list[Hit], ms: float) -> None:
    if not hits:
        print(f"  no results ({ms:.2f} ms)")
        return
    for rank, hit in enumerate(hits, 1):
        print(f"{rank:>2}. {hit.score:7.3f}  {hit.doc_id}")
        print(f"      {mark(hit.snippet)}")
    print(f"  {len(hits)} hit(s) in {ms:.2f} ms")


def print_explain(engine: SearchEngine, query: str, hit: Hit, ranker: str) -> None:
    ex = engine.explain(query, hit.doc_id, ranker=ranker)
    print(f"  explain {ex.doc_id} [{ranker}] N={ex.n_docs} avgdl={ex.avgdl:.1f}")
    print(f"  {'term':<24}{'tf':>4}{'df':>6}{'idf':>8}{'dl':>7}{'contribution':>14}")
    for t in ex.terms:
        print(
            f"  {t.term:<24}{t.tf:>4}{t.df:>6}{t.idf:>8.3f}{t.doc_length:>7}{t.contribution:>14.4f}"
        )
    print(f"  {'total':<49}{ex.score:>14.4f}")


def run_query(engine: SearchEngine, query: str, args: argparse.Namespace) -> None:
    t0 = time.perf_counter()
    hits = engine.search(query, mode=args.mode, limit=args.limit, ranker=args.ranker)
    ms = (time.perf_counter() - t0) * 1000
    print_hits(hits, ms)
    if args.explain and hits:
        if args.explain <= len(hits):
            print_explain(engine, query, hits[args.explain - 1], args.ranker)
        else:
            print(f"  --explain {args.explain}: only {len(hits)} hit(s)")


def bench(engine: SearchEngine, build_s: float, args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "index.json"
        engine.index.save(path)
        size_mb = path.stat().st_size / 1_000_000
    print(f"index time : {build_s:.2f} s")
    print(f"documents  : {engine.index.N}")
    print(f"unique terms: {engine.index.terms_count}")
    print(f"index size : {size_mb:.2f} MB (JSON)")
    for mode in ("all", "any"):
        timings: list[tuple[float, str]] = []
        for query in BENCH_QUERIES:
            runs = []
            for _ in range(5):
                t0 = time.perf_counter()
                engine.search(query, mode=mode, ranker=args.ranker)
                runs.append((time.perf_counter() - t0) * 1000)
            timings.append((statistics.median(runs), query))
        values = sorted(t for t, _ in timings)
        p50 = statistics.median(values)
        p95 = values[min(len(values) - 1, int(0.95 * len(values)))]
        slowest = max(timings)
        print(
            f"query latency mode={mode} ranker={args.ranker}: {len(values)} queries, "
            f"p50 {p50:.2f} ms, p95 {p95:.2f} ms, slowest {slowest[0]:.2f} ms ({slowest[1]})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="folder with .md/.txt files")
    parser.add_argument("--ranker", choices=["tfidf", "bm25"], default="bm25")
    parser.add_argument("--mode", choices=["all", "any"], default="all")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--explain", type=int, default=0, metavar="N", help="explain the Nth hit")
    parser.add_argument("--bench", action="store_true", help="print index stats and latency")
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(
            f"Folder not found: {args.dir}\n"
            "Pass --dir <folder>, or fetch the FastAPI docs with: uv run python -m mnemonic.ingest",
            file=sys.stderr,
        )
        return 2
    docs, empty, bad = load_corpus(args.dir)
    if not docs:
        print(f"No non-empty {', '.join(sorted(EXTENSIONS))} files in {args.dir}", file=sys.stderr)
        return 2

    engine = SearchEngine()
    t0 = time.perf_counter()
    for doc_id, text in docs.items():
        engine.add_document(doc_id, text)
    build_s = time.perf_counter() - t0
    print(f"Indexed {len(docs)} files from {args.dir} in {build_s:.2f} s")
    if empty:
        print(f"  skipped {empty} empty file(s)")
    if bad:
        print(f"  {bad} file(s) were not UTF-8: undecodable bytes replaced")

    if args.bench:
        bench(engine, build_s, args)
        return 0

    print('Query syntax: foo bar | "exact phrase" | -word. Empty line to quit.')
    while True:
        try:
            query = input("search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            break
        run_query(engine, query, args)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
