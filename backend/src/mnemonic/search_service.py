"""The search engine inside the backend: index lifecycle, thread-safety and ownership.

The `search/` package stays pure (no DB, no web). This module is the glue:

* **Build** from every chunk in the DB at startup, off to the side, then swap it in.
* **Incremental updates** (`add_chunks` / `remove_chunks`) are called by the code that writes the
  DB, right after a successful commit (see main.py). If the DB write fails they are never reached.
* **Ownership**: a chunk is visible if it is shared (knowledge base) or owned by the caller.
  `allowed_ids` computes that set; the engine filters by it BEFORE ranking.

Single-process assumption: the index lives in this process's memory. Render runs one worker; with
several workers each would need its own rebuild and updates would not reach the others (ADR 0005).
"""

import json
import logging
import threading
import time
import tracemalloc
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from mnemonic.search import Explanation, SearchEngine
from mnemonic.search import Hit as SearchHit
from mnemonic.search.query import parse_query
from mnemonic.store import IndexRow, Store

logger = logging.getLogger(__name__)

# The lexical "I don't know" gate only looks at short queries (see retrieval.py).
LEXICAL_GATE_MAX_TERMS = 3


def index_text(row: IndexRow) -> str:
    """What is indexed for a chunk: the heading too, so `CORS` finds the page titled CORS."""
    return f"{row.heading}\n{row.content}"


@dataclass(frozen=True)
class BuildStats:
    chunks: int
    terms: int
    build_seconds: float
    memory_mb: float | None
    memory_source: str  # "rss" (Linux /proc) or "tracemalloc"


def _rss_mb() -> float | None:
    """Resident memory of this process in MB from /proc/self/status (Linux), else None."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


class SearchService:
    def __init__(self) -> None:
        # One lock for everything. Writers need it (dicts are not safe to change while another
        # thread iterates them: "dictionary changed size during iteration", or a half-applied
        # add). Readers take it too: a query is a few milliseconds of in-memory work, and a
        # copy-on-write snapshot of the whole index per update would cost far more than it saves.
        # The startup build avoids long lock holds differently: it fills a NEW engine without
        # the lock and swaps the reference in.
        self._lock = threading.Lock()
        self._engine = SearchEngine()
        self._shared: set[str] = set()
        self._ready = False
        # While a build runs, updates are also recorded here and replayed on the new engine, so
        # an upload that lands mid-build is not lost.
        self._journal: list[tuple[str, list]] | None = None

    @property
    def ready(self) -> bool:
        return self._ready

    # --- lifecycle ---------------------------------------------------------------------
    def build(self, rows: Iterable[IndexRow]) -> BuildStats:
        with self._lock:
            self._journal = []
        rss_before = _rss_mb()
        traced_here = rss_before is None and not tracemalloc.is_tracing()
        if traced_here:
            tracemalloc.start()
        started = time.perf_counter()
        try:
            engine, shared, count = SearchEngine(), set(), 0
            for row in rows:
                self._apply_add(engine, shared, row)
                count += 1
            seconds = time.perf_counter() - started
            rss_after = _rss_mb()
            if rss_before is not None and rss_after is not None:
                memory, source = rss_after - rss_before, "rss"
            elif traced_here:
                memory, source = tracemalloc.get_traced_memory()[0] / 2**20, "tracemalloc"
            else:
                memory, source = None, "none"
            with self._lock:
                for op, payload in self._journal or []:
                    if op == "add":
                        for row in payload:
                            self._apply_add(engine, shared, row)
                    else:
                        for cid in payload:
                            self._apply_remove(engine, shared, str(cid))
                self._engine, self._shared, self._ready = engine, shared, True
        finally:
            if traced_here:
                tracemalloc.stop()
            with self._lock:
                self._journal = None
        stats = BuildStats(
            count, self._engine.index.terms_count, seconds, memory and round(memory, 1), source
        )
        logger.info(
            json.dumps(
                {
                    "event": "search_index_built",
                    "chunks": stats.chunks,
                    "terms": stats.terms,
                    "build_seconds": round(stats.build_seconds, 2),
                    "memory_mb": stats.memory_mb,
                    "memory_source": stats.memory_source,
                    "rss_mb": None if _rss_mb() is None else round(_rss_mb(), 1),
                }
            )
        )
        return stats

    @staticmethod
    def _apply_add(engine: SearchEngine, shared: set[str], row: IndexRow) -> None:
        engine.add_document(str(row.id), index_text(row))
        if row.owner_id is None:
            shared.add(str(row.id))

    @staticmethod
    def _apply_remove(engine: SearchEngine, shared: set[str], doc_id: str) -> None:
        engine.remove_document(doc_id)
        shared.discard(doc_id)

    def add_chunks(self, rows: Iterable[IndexRow]) -> None:
        """Call AFTER the DB commit that stored these chunks."""
        rows = list(rows)
        with self._lock:
            for row in rows:
                self._apply_add(self._engine, self._shared, row)
            if self._journal is not None:
                self._journal.append(("add", rows))

    def remove_chunks(self, chunk_ids: Iterable[int]) -> None:
        """Call AFTER the DB commit that deleted these chunks."""
        ids = list(chunk_ids)
        with self._lock:
            for cid in ids:
                self._apply_remove(self._engine, self._shared, str(cid))
            if self._journal is not None:
                self._journal.append(("remove", ids))

    def __len__(self) -> int:
        with self._lock:
            return self._engine.index.N

    # --- ownership ---------------------------------------------------------------------
    def allowed_ids(self, owned_chunk_ids: Iterable[int] = ()) -> set[str]:
        """Shared chunks (cached here) plus the caller's own (the caller reads them from the DB,
        the source of truth). Everything else is never searchable for this user."""
        with self._lock:
            shared = set(self._shared)
        return shared | {str(i) for i in owned_chunk_ids}

    # --- reading -----------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        allowed_ids: Collection[str],
        mode: str = "all",
        limit: int = 10,
        ranker: str = "bm25",
    ) -> list[SearchHit]:
        # allowed_ids is required (no default): there is no way to search "everything" by accident.
        with self._lock:
            return self._engine.search(
                query, mode=mode, limit=limit, allowed_ids=allowed_ids, ranker=ranker
            )

    def explain(
        self, query: str, chunk_id: int, *, allowed_ids: Collection[str], ranker: str = "bm25"
    ) -> Explanation:
        """Raises KeyError for an unknown chunk AND for one outside `allowed_ids`."""
        doc_id = str(chunk_id)
        if doc_id not in allowed_ids:
            raise KeyError(doc_id)
        with self._lock:
            return self._engine.explain(query, doc_id, ranker=ranker)

    def lexical_all(
        self, query: str, *, allowed_ids: Collection[str], limit: int
    ) -> tuple[set[int], float]:
        """For the lexical "I don't know" gate: ids of the visible chunks that contain ALL the
        non-stop query terms (only when the query has 1..LEXICAL_GATE_MAX_TERMS of them), and the
        largest document-frequency ratio among those terms (1.0 = a term in every chunk)."""
        terms = parse_query(query).scoring_terms
        if not terms or len(terms) > LEXICAL_GATE_MAX_TERMS:
            return set(), 1.0
        with self._lock:
            hits = self._engine.search(
                query, mode="all", limit=limit, allowed_ids=allowed_ids, ranker="bm25"
            )
            index = self._engine.index
            max_df = max(index.df(t) for t in terms) / index.N if index.N else 1.0
        return {int(h.doc_id) for h in hits}, max_df


def build_from_store(service: SearchService, store: Store) -> BuildStats | None:
    """Startup build in a worker thread. Never raises: without an index the app still answers
    (chat falls back to vector search, /search says 503 until a restart fixes the cause)."""
    try:
        return service.build(store.index_rows())
    except Exception:
        logger.exception("could not build the search index")
        return None


@lru_cache
def get_search_service() -> SearchService:
    return SearchService()
