"""Chat storage: sessions, messages and the LLM call log. Raw SQL via psycopg, no ORM."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from mnemonic.ingest import db as chunks_db
from mnemonic.ingest.chunker import Chunk as NewChunk

# Created at app startup; every statement is idempotent. No migrations yet (Alembic: lab 21).
# The chunks / documents tables are created by `chunks_db.SCHEMA`, which init_schema runs first.
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id         bigserial PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       text NOT NULL CHECK (role IN ('user', 'assistant')),
    content    text NOT NULL,
    sources    jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_idx ON messages (session_id, id);

CREATE TABLE IF NOT EXISTS llm_calls (
    id         bigserial PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    model      text NOT NULL,
    tokens_in  integer NOT NULL,
    tokens_out integer NOT NULL,
    cost_usd   numeric(12, 8) NOT NULL,
    latency_ms integer NOT NULL,
    status     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class StoredMessage:
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict] | None
    created_at: datetime
    id: int = 0  # messages.id; last so that positional construction stays valid


@dataclass(frozen=True)
class LLMCall:
    session_id: UUID
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    status: str


@dataclass(frozen=True)
class Chunk:
    """A knowledge-base chunk as stored (no vector): what a citation points to."""

    id: int
    file_path: str
    heading: str
    content: str


@dataclass(frozen=True)
class StoredDocument:
    """An uploaded document (metadata only)."""

    id: int
    filename: str
    created_at: datetime
    chunks: int


class TooManyDocuments(Exception):
    """The owner already has the maximum number of documents."""


class Store(Protocol):
    """Blocking API: call it from a worker thread (asyncio.to_thread)."""

    def init_schema(self) -> None: ...

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> int:
        """Append a message and return its id; the session row is created on first use."""
        ...

    def get_messages(self, session_id: UUID) -> list[StoredMessage]: ...

    def log_llm_call(self, call: LLMCall) -> None: ...

    def get_chunks(self, ids: list[int], owner_id: UUID | None = None) -> list[Chunk]:
        """The chunks among `ids` that `owner_id` may see: shared ones and their own. Unknown
        ids and other owners' chunks are both simply absent (so ids cannot be enumerated)."""
        ...

    def count_documents(self, owner_id: UUID) -> int: ...

    def list_documents(self, owner_id: UUID) -> list[StoredDocument]: ...

    def add_document(
        self,
        owner_id: UUID,
        filename: str,
        chunks: Sequence[NewChunk],
        vectors: Sequence[np.ndarray],
        max_documents: int,
    ) -> StoredDocument:
        """Store a document with its chunks atomically; raises TooManyDocuments at the limit."""
        ...

    def delete_document(self, owner_id: UUID, document_id: int) -> bool:
        """Delete the owner's document and its chunks. False if it is not theirs / not there."""
        ...


class PgStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _connect(self) -> psycopg.Connection:
        if not self._url:
            raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
        # A connection per call, like PgRetriever (pooling comes later). The `with` in the
        # callers commits and closes it.
        return psycopg.connect(self._url)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(chunks_db.SCHEMA)  # chunks + documents (+ the M7a columns)
            conn.execute(SCHEMA)

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> int:
        with self._connect() as conn:  # one transaction: the session row and the message
            conn.execute(
                "INSERT INTO sessions (id) VALUES (%s) ON CONFLICT DO NOTHING", (session_id,)
            )
            row = conn.execute(
                "INSERT INTO messages (session_id, role, content, sources) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (session_id, role, content, None if sources is None else Jsonb(sources)),
            ).fetchone()
        return row[0]

    def get_messages(self, session_id: UUID) -> list[StoredMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, sources, created_at, id FROM messages "
                "WHERE session_id = %s ORDER BY id",
                (session_id,),
            ).fetchall()
        return [StoredMessage(*row) for row in rows]

    def get_chunks(self, ids: list[int], owner_id: UUID | None = None) -> list[Chunk]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, file_path, heading, content FROM chunks "
                "WHERE id = ANY(%s) AND (owner_id IS NULL OR owner_id = %s) ORDER BY id",
                (ids, owner_id),
            ).fetchall()
        return [Chunk(*row) for row in rows]

    def count_documents(self, owner_id: UUID) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count(*) FROM documents WHERE owner_id = %s", (owner_id,)
            ).fetchone()
        return row[0]

    def list_documents(self, owner_id: UUID) -> list[StoredDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT d.id, d.filename, d.created_at, count(c.id) FROM documents d "
                "LEFT JOIN chunks c ON c.document_id = d.id "
                "WHERE d.owner_id = %s GROUP BY d.id ORDER BY d.id",
                (owner_id,),
            ).fetchall()
        return [StoredDocument(*row) for row in rows]

    def add_document(
        self,
        owner_id: UUID,
        filename: str,
        chunks: Sequence[NewChunk],
        vectors: Sequence[np.ndarray],
        max_documents: int,
    ) -> StoredDocument:
        with self._connect() as conn:  # one transaction: an error leaves no half document
            register_vector(conn)
            # Serialise this owner's uploads, so two parallel ones cannot both pass the limit.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(owner_id),))
            (count,) = conn.execute(
                "SELECT count(*) FROM documents WHERE owner_id = %s", (owner_id,)
            ).fetchone()
            if count >= max_documents:
                raise TooManyDocuments
            doc_id, created_at = conn.execute(
                "INSERT INTO documents (owner_id, filename) VALUES (%s, %s) "
                "RETURNING id, created_at",
                (owner_id, filename),
            ).fetchone()
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (file_path, heading, chunk_index, content, content_hash, "
                    "embedding, document_id, owner_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    [
                        (
                            c.file_path,
                            c.heading,
                            c.chunk_index,
                            c.content,
                            # UNIQUE column: the document id keeps equal text of two uploads apart.
                            hashlib.sha256(
                                f"{doc_id}\0{c.chunk_index}\0{c.content}".encode()
                            ).hexdigest(),
                            v,
                            doc_id,
                            owner_id,
                        )
                        for c, v in zip(chunks, vectors, strict=True)
                    ],
                )
        return StoredDocument(doc_id, filename, created_at, len(chunks))

    def delete_document(self, owner_id: UUID, document_id: int) -> bool:
        with self._connect() as conn:
            # The chunks go with it: chunks.document_id is ON DELETE CASCADE.
            row = conn.execute(
                "DELETE FROM documents WHERE id = %s AND owner_id = %s RETURNING id",
                (document_id, owner_id),
            ).fetchone()
        return row is not None

    def log_llm_call(self, call: LLMCall) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO llm_calls "
                "(session_id, model, tokens_in, tokens_out, cost_usd, latency_ms, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    call.session_id,
                    call.model,
                    call.tokens_in,
                    call.tokens_out,
                    call.cost_usd,
                    call.latency_ms,
                    call.status,
                ),
            )
