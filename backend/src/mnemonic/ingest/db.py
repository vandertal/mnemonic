"""Raw-SQL storage for chunks + vectors (psycopg, no ORM). The schema lives in migrations/."""

import hashlib
from collections.abc import Iterable, Sequence
from uuid import UUID

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from mnemonic.ingest.chunker import Chunk


def content_hash(chunk: Chunk) -> str:
    """Identity of a chunk: same file + same text -> same hash (the path keeps equal
    boilerplate in two different files from colliding on the UNIQUE constraint)."""
    return hashlib.sha256(f"{chunk.file_path}\0{chunk.content}".encode()).hexdigest()


def connect(database_url: str) -> psycopg.Connection:
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
    conn = psycopg.connect(database_url, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")  # must exist before register_vector
    register_vector(conn)
    return conn


def existing_hashes(conn: psycopg.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT content_hash FROM chunks")}


def upsert_chunks(
    conn: psycopg.Connection, chunks: Sequence[Chunk], vectors: Iterable[np.ndarray]
) -> int:
    """Insert new chunks, skip existing content_hash values. Returns the inserted count."""
    sql = """
        INSERT INTO chunks (file_path, heading, chunk_index, content, content_hash, embedding)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (content_hash) DO NOTHING
    """
    rows = [
        (c.file_path, c.heading, c.chunk_index, c.content, content_hash(c), v)
        for c, v in zip(chunks, vectors, strict=True)
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        return cur.rowcount


def count(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]


def search(
    conn: psycopg.Connection, query_vec: np.ndarray, k: int = 3, owner_id: UUID | None = None
) -> list[tuple]:
    """Top-k by cosine similarity: (id, similarity, file_path, heading, content).

    Only shared chunks (owner_id IS NULL) and the caller's own are visible; with no owner,
    only the shared ones."""
    return conn.execute(
        """
        SELECT id, 1 - (embedding <=> %s) AS similarity, file_path, heading, content
        FROM chunks WHERE owner_id IS NULL OR owner_id = %s
        ORDER BY embedding <=> %s LIMIT %s
        """,
        (query_vec, owner_id, query_vec, k),
    ).fetchall()
