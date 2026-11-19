"""Retrieval: embed the question, find the top-k closest chunks in pgvector."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from mnemonic.ingest import db
from mnemonic.ingest.embedder import embed_query


@dataclass(frozen=True)
class Hit:
    id: int
    similarity: float  # 1 - cosine distance; higher is closer
    file_path: str
    heading: str
    content: str


class Retriever(Protocol):
    """question -> hits, best first. Blocking: call it from a worker thread."""

    def __call__(self, question: str, owner_id: UUID | None = None) -> list[Hit]: ...


def retrieve(conn, question: str, k: int, owner_id: UUID | None = None) -> list[Hit]:
    """Shared chunks plus the owner's own (if any)."""
    rows = db.search(conn, embed_query(question), k, owner_id)
    return [Hit(*row) for row in rows]


class PgRetriever:
    def __init__(self, database_url: str, k: int) -> None:
        self._url = database_url
        self._k = k

    def __call__(self, question: str, owner_id: UUID | None = None) -> list[Hit]:
        # A connection per question is simple and fine at this scale (pooling comes later).
        with db.connect(self._url) as conn:
            return retrieve(conn, question, self._k, owner_id)
