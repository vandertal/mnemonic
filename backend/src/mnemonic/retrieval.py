"""Retrieval: find the chunks that may answer a question, and decide if there is an answer at all.

Three modes (`RETRIEVAL_MODE`):
  vector  pgvector cosine top-k only: the original behaviour, byte for byte.
  bm25    the in-memory lexical index only (search_service.py).
  hybrid  Reciprocal Rank Fusion of both.
"""

import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

import numpy as np

from mnemonic.ingest import db
from mnemonic.ingest.embedder import embed_query
from mnemonic.search_service import SearchService

logger = logging.getLogger(__name__)

RRF_K = 60  # the constant from the original RRF paper; it damps the weight of the very top ranks


@dataclass(frozen=True)
class Hit:
    id: int
    similarity: float  # 1 - cosine distance; higher is closer
    file_path: str
    heading: str
    content: str
    # Set by the lexical retriever, used by the "I don't know" gate. Defaults keep vector-only
    # hits (and test doubles) exactly as they were.
    lexical_all: bool = False  # this chunk contains ALL non-stop query terms (short queries only)
    lexical_max_df: float = 1.0  # share of all chunks containing the most common query term


class Retriever(Protocol):
    """question -> hits, best first. Blocking: call it from a worker thread."""

    def __call__(self, question: str, owner_id: UUID | None = None) -> list[Hit]: ...


# --- fusion -------------------------------------------------------------------------------
def rrf(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: score(id) = sum over rankings of 1 / (k + rank), rank from 1.

    Only RANKS are used, never the scores: cosine similarity and BM25 live on unrelated scales,
    so mixing the raw numbers would need calibration. Equal scores keep first-seen order."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: -item[1])  # sorted() is stable


# --- the "I don't know" gate --------------------------------------------------------------
# Each gate answers: "is there anything relevant enough to send to the LLM?". They are compared
# in eval/retrieval_ablation.py; ANSWER_GATE below is the one the chat uses.
def gate_vector(hits: Sequence[Hit], threshold: float) -> bool:
    """(a) The original rule: the closest chunk is similar enough."""
    return bool(hits) and max(h.similarity for h in hits) >= threshold


def gate_vector_or_lexical(hits: Sequence[Hit], threshold: float) -> bool:
    """(b) Vector gate, OR a chunk holds every non-stop query term (queries of <= 3 terms)."""
    return gate_vector(hits, threshold) or any(h.lexical_all for h in hits)


MAX_COMMON_TERM_DF = 0.2


def gate_vector_or_specific_lexical(hits: Sequence[Hit], threshold: float) -> bool:
    """(c) Like (b), but a term found in more than 20 % of all chunks ("python") says nothing
    about the topic, so a match on it alone does not open the gate."""
    return gate_vector(hits, threshold) or any(
        h.lexical_all and h.lexical_max_df <= MAX_COMMON_TERM_DF for h in hits
    )


GATES: dict[str, Callable[[Sequence[Hit], float], bool]] = {
    "a": gate_vector,
    "b": gate_vector_or_lexical,
    "c": gate_vector_or_specific_lexical,
}
ANSWER_GATE = "b"


def is_answerable(hits: Sequence[Hit], threshold: float, mode: str = "hybrid") -> bool:
    """The gate the chat uses. `vector` mode always uses (a): it must behave exactly as before."""
    gate = GATES["a"] if mode == "vector" else GATES[ANSWER_GATE]
    return gate(hits, threshold)


# --- data access --------------------------------------------------------------------------
class SourceSession(Protocol):
    """Chunk access over ONE connection (a Neon connection is expensive to open)."""

    def vector_search(self, qvec: np.ndarray, owner_id: UUID | None, n: int) -> list[Hit]: ...

    def fetch(self, qvec: np.ndarray, ids: Sequence[int], owner_id: UUID | None) -> list[Hit]: ...

    def owned_ids(self, owner_id: UUID) -> list[int]: ...


class ChunkSource(Protocol):
    def session(self) -> AbstractContextManager[SourceSession]: ...


class _PgSession:
    def __init__(self, conn) -> None:
        self._conn = conn

    def vector_search(self, qvec, owner_id, n) -> list[Hit]:
        return [Hit(*row) for row in db.search(self._conn, qvec, n, owner_id)]

    def fetch(self, qvec, ids, owner_id) -> list[Hit]:
        return [Hit(*row) for row in db.fetch_by_ids(self._conn, qvec, ids, owner_id)]

    def owned_ids(self, owner_id) -> list[int]:
        return db.owned_chunk_ids(self._conn, owner_id)


class PgSource:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    @contextmanager
    def session(self) -> Iterator[SourceSession]:
        # A connection per question is simple and fine at this scale (pooling comes later).
        with db.connect(self._url) as conn:
            yield _PgSession(conn)


def retrieve(conn, question: str, k: int, owner_id: UUID | None = None) -> list[Hit]:
    """Shared chunks plus the owner's own (if any). Pure vector search."""
    rows = db.search(conn, embed_query(question), k, owner_id)
    return [Hit(*row) for row in rows]


class HybridRetriever:
    def __init__(
        self,
        source: ChunkSource,
        k: int,
        mode: str = "hybrid",
        search: SearchService | None = None,
        candidates: int = 20,
        embed: Callable[[str], np.ndarray] = embed_query,
    ) -> None:
        self._source = source
        self._k = k
        self._mode = mode
        self._search = search
        self._candidates = max(candidates, k)
        self._embed = embed

    def __call__(self, question: str, owner_id: UUID | None = None) -> list[Hit]:
        qvec = self._embed(question)
        search = self._search
        lexical = self._mode != "vector" and search is not None and search.ready
        with self._source.session() as src:
            if not lexical:  # vector mode, or the index is not built yet: today's behaviour
                return src.vector_search(qvec, owner_id, self._k)
            assert search is not None
            # Visible = shared + the caller's own chunks. The owned ids come from the DB (the
            # source of truth); the engine filters by this set BEFORE ranking.
            allowed = search.allowed_ids(src.owned_ids(owner_id) if owner_id else ())
            lex = search.search(question, mode="any", limit=self._candidates, allowed_ids=allowed)
            lex_ids = [int(h.doc_id) for h in lex]
            if self._mode == "bm25":
                vec_hits: list[Hit] = []
                ids = lex_ids[: self._k]
            else:
                vec_hits = src.vector_search(qvec, owner_id, self._candidates)
                fused = rrf([[h.id for h in vec_hits], lex_ids])
                ids = [chunk_id for chunk_id, _ in fused[: self._k]]
            known = {h.id: h for h in vec_hits}
            missing = [i for i in ids if i not in known]
            if missing:  # lexical-only hits: the DB gives text and similarity (owner re-checked)
                known.update({h.id: h for h in src.fetch(qvec, missing, owner_id)})
            hits = [known[i] for i in ids if i in known]  # an id the DB no longer has is dropped
            all_ids, max_df = search.lexical_all(question, allowed_ids=allowed, limit=len(allowed))
            return [replace(h, lexical_all=h.id in all_ids, lexical_max_df=max_df) for h in hits]


class PgRetriever(HybridRetriever):
    def __init__(
        self,
        database_url: str,
        k: int,
        mode: str = "vector",
        search: SearchService | None = None,
        candidates: int = 20,
    ) -> None:
        super().__init__(PgSource(database_url), k, mode, search, candidates)
