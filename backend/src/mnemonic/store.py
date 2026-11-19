"""Chat storage: sessions, messages and the LLM call log. Raw SQL via psycopg, no ORM."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

# Created at app startup; every statement is idempotent. No migrations yet (Alembic: lab 21).
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


@dataclass(frozen=True)
class LLMCall:
    session_id: UUID
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    status: str


class Store(Protocol):
    """Blocking API: call it from a worker thread (asyncio.to_thread)."""

    def init_schema(self) -> None: ...

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> None:
        """Append a message; the session row is created on first use."""
        ...

    def get_messages(self, session_id: UUID) -> list[StoredMessage]: ...

    def log_llm_call(self, call: LLMCall) -> None: ...


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
            conn.execute(SCHEMA)

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> None:
        with self._connect() as conn:  # one transaction: the session row and the message
            conn.execute(
                "INSERT INTO sessions (id) VALUES (%s) ON CONFLICT DO NOTHING", (session_id,)
            )
            conn.execute(
                "INSERT INTO messages (session_id, role, content, sources) VALUES (%s, %s, %s, %s)",
                (session_id, role, content, None if sources is None else Jsonb(sources)),
            )

    def get_messages(self, session_id: UUID) -> list[StoredMessage]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, sources, created_at FROM messages "
                "WHERE session_id = %s ORDER BY id",
                (session_id,),
            ).fetchall()
        return [StoredMessage(*row) for row in rows]

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
