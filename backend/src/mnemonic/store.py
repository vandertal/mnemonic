"""Chat storage: sessions, messages and the LLM call log. Raw SQL via psycopg, no ORM."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal, Protocol
from uuid import UUID

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from mnemonic.config import get_settings
from mnemonic.ingest.chunker import Chunk as NewChunk


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
    # ids of the chunks just stored (filled by add_document only; the search index needs them)
    chunk_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class IndexRow:
    """What the search index needs of a chunk. `owner_id` None = shared knowledge base."""

    id: int
    owner_id: UUID | None
    heading: str
    content: str


STATS_DAYS = 7
CHANNELS = ("web", "telegram")
DEFAULT_TITLE = "New chat"
TITLE_FROM_MESSAGE_CHARS = 60


@dataclass(frozen=True)
class Session:
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    created_at: datetime


class EmailTaken(Exception):
    """An account with this email already exists."""


class SessionNotFound(Exception):
    """The session does not exist or is not the caller's (the two are never told apart)."""


class TooManyDocuments(Exception):
    """The owner already has the maximum number of documents."""


class Store(Protocol):
    """Blocking API: call it from a worker thread (asyncio.to_thread)."""

    def create_user(self, email: str, password_hash: str) -> User:
        """Insert an account; raises EmailTaken if the (lower-cased) email exists."""
        ...

    def get_user_by_email(self, email: str) -> tuple[User, str] | None:
        """The user and their password hash, or None."""
        ...

    def get_user(self, user_id: UUID) -> User | None: ...

    def find_telegram_user(self, telegram_id: int) -> User | None:
        """The Mnemonic user behind a Telegram id, or None if they never wrote to the bot."""
        ...

    def get_or_create_telegram_user(
        self, telegram_id: int, password_hash: str
    ) -> tuple[User, bool]:
        """The user behind a Telegram id; the first call creates the user and the link. Safe under
        concurrent first messages (one user, one link). Returns (user, created_by_this_call)."""
        ...

    def delete_user(self, user_id: UUID) -> bool:
        """Delete the account; sessions, documents and chunks go with it (ON DELETE CASCADE)."""
        ...

    def create_session(self, user_id: UUID, title: str | None = None) -> Session: ...

    def list_sessions(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Session], int]:
        """One page of the user's sessions (newest `updated_at` first) and the total count."""
        ...

    def get_session(self, user_id: UUID, session_id: UUID) -> Session | None:
        """None if it does not exist OR belongs to someone else."""
        ...

    def rename_session(self, user_id: UUID, session_id: UUID, title: str) -> Session | None: ...

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool: ...

    def add_message(
        self,
        user_id: UUID,
        session_id: UUID,
        role: str,
        content: str,
        sources: list[dict] | None = None,
    ) -> int:
        """Append a message to the user's session and return its id. Bumps `updated_at`; a user
        message also becomes the title while it is still the default. Raises SessionNotFound."""
        ...

    def get_messages(self, user_id: UUID, session_id: UUID) -> list[StoredMessage] | None:
        """Messages oldest first, or None if the session is not the user's / not there."""
        ...

    def log_llm_call(self, call: LLMCall) -> None: ...

    def log_event(self, name: str, user_id: UUID | None, props: dict) -> None:
        """Append one product event (see mnemonic.events). Props: small flags, never text."""
        ...

    def event_stats(self, days: int = STATS_DAYS) -> dict:
        """Aggregates for /admin/stats: see PgStore.event_stats for the shape."""
        ...

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

    def delete_document(self, owner_id: UUID, document_id: int) -> list[int] | None:
        """Delete the owner's document and its chunks; returns the deleted chunk ids, or None if
        the document is not theirs / not there."""
        ...

    def owned_chunk_ids(self, owner_id: UUID) -> list[int]:
        """Ids of the chunks that belong to this owner's documents (not the shared ones)."""
        ...

    def index_rows(self) -> list[IndexRow]:
        """Every chunk (shared and owned): the input of the startup index build."""
        ...


def telegram_email(telegram_id: int) -> str:
    """The placeholder email of a Telegram user. `.invalid` is a reserved TLD: it can never be a
    real mailbox, and nobody can sign in with it because the password hash is of a random secret."""
    return f"tg-{telegram_id}@telegram.invalid"


def first_line_title(content: str) -> str:
    """A chat title from its first message: whitespace collapsed, cut to 60 characters."""
    return " ".join(content.split())[:TITLE_FROM_MESSAGE_CHARS]


class PgStore:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _connect(self) -> psycopg.Connection:
        if not self._url:
            raise RuntimeError("DATABASE_URL is not set (see backend/.env.example)")
        # A connection per call, like PgRetriever (pooling comes later). The `with` in the
        # callers commits and closes it.
        return psycopg.connect(self._url)

    def create_user(self, email: str, password_hash: str) -> User:
        # No "check, then insert": two parallel requests could both pass the check. The UNIQUE
        # constraint is the only race-free referee, so we insert and translate its error.
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (%s, %s) "
                    "RETURNING id, email, created_at",
                    (email, password_hash),
                ).fetchone()
        except psycopg.errors.UniqueViolation:
            raise EmailTaken from None
        return User(*row)

    def get_user_by_email(self, email: str) -> tuple[User, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, created_at, password_hash FROM users WHERE email = %s",
                (email,),
            ).fetchone()
        return None if row is None else (User(*row[:3]), row[3])

    def get_user(self, user_id: UUID) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, created_at FROM users WHERE id = %s", (user_id,)
            ).fetchone()
        return None if row is None else User(*row)

    def delete_user(self, user_id: UUID) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "DELETE FROM users WHERE id = %s RETURNING id", (user_id,)
            ).fetchone()
        return row is not None

    def find_telegram_user(self, telegram_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT u.id, u.email, u.created_at FROM telegram_accounts t "
                "JOIN users u ON u.id = t.user_id WHERE t.telegram_id = %s",
                (telegram_id,),
            ).fetchone()
        return None if row is None else User(*row)

    def get_or_create_telegram_user(
        self, telegram_id: int, password_hash: str
    ) -> tuple[User, bool]:
        with self._connect() as conn:  # one transaction: the user and the link exist together
            # Serialise first messages of the SAME telegram id: the second waits here, then sees
            # the link the first one committed. (Different ids do not block each other.)
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (telegram_id,))
            found = conn.execute(
                "SELECT u.id, u.email, u.created_at FROM telegram_accounts t "
                "JOIN users u ON u.id = t.user_id WHERE t.telegram_id = %s",
                (telegram_id,),
            ).fetchone()
            if found is not None:
                return User(*found), False
            row = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) "
                "RETURNING id, email, created_at",
                (telegram_email(telegram_id), password_hash),
            ).fetchone()
            conn.execute(
                "INSERT INTO telegram_accounts (telegram_id, user_id) VALUES (%s, %s)",
                (telegram_id, row[0]),
            )
        return User(*row), True

    # Ownership is part of every query below (`AND user_id = %s`): we never fetch a row and compare
    # the owner in Python, so there is no code path that forgets the comparison.

    def create_session(self, user_id: UUID, title: str | None = None) -> Session:
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO sessions (id, user_id, title) VALUES (gen_random_uuid(), %s, %s) "
                "RETURNING id, title, created_at, updated_at",
                (user_id, title or DEFAULT_TITLE),
            ).fetchone()
        return Session(*row)

    def list_sessions(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Session], int]:
        with self._connect() as conn:
            # `id` breaks ties, so equal timestamps cannot reorder rows between two pages.
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE user_id = %s "
                "ORDER BY updated_at DESC, id LIMIT %s OFFSET %s",
                (user_id, limit, offset),
            ).fetchall()
            (total,) = conn.execute(
                "SELECT count(*) FROM sessions WHERE user_id = %s", (user_id,)
            ).fetchone()
        return [Session(*row) for row in rows], total

    def get_session(self, user_id: UUID, session_id: UUID) -> Session | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions "
                "WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            ).fetchone()
        return None if row is None else Session(*row)

    def rename_session(self, user_id: UUID, session_id: UUID, title: str) -> Session | None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE sessions SET title = %s WHERE id = %s AND user_id = %s "
                "RETURNING id, title, created_at, updated_at",
                (title, session_id, user_id),
            ).fetchone()
        return None if row is None else Session(*row)

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        with self._connect() as conn:
            # messages and llm_calls go with it: both reference sessions ON DELETE CASCADE.
            row = conn.execute(
                "DELETE FROM sessions WHERE id = %s AND user_id = %s RETURNING id",
                (session_id, user_id),
            ).fetchone()
        return row is not None

    def add_message(
        self,
        user_id: UUID,
        session_id: UUID,
        role: str,
        content: str,
        sources: list[dict] | None = None,
    ) -> int:
        new_title = (first_line_title(content) or None) if role == "user" else None
        with self._connect() as conn:  # one transaction: the session bump and the message
            bumped = conn.execute(
                "UPDATE sessions SET updated_at = now(), "
                "title = CASE WHEN title = %s THEN COALESCE(%s::text, title) ELSE title END "
                "WHERE id = %s AND user_id = %s RETURNING id",
                (DEFAULT_TITLE, new_title, session_id, user_id),
            ).fetchone()
            if bumped is None:
                raise SessionNotFound
            row = conn.execute(
                "INSERT INTO messages (session_id, role, content, sources) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (session_id, role, content, None if sources is None else Jsonb(sources)),
            ).fetchone()
        return row[0]

    def get_messages(self, user_id: UUID, session_id: UUID) -> list[StoredMessage] | None:
        with self._connect() as conn:
            owned = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s AND user_id = %s", (session_id, user_id)
            ).fetchone()
            if owned is None:
                return None
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
            chunk_ids = tuple(
                r[0]
                for r in conn.execute(
                    "SELECT id FROM chunks WHERE document_id = %s ORDER BY chunk_index, id",
                    (doc_id,),
                )
            )
        return StoredDocument(doc_id, filename, created_at, len(chunks), chunk_ids)

    def delete_document(self, owner_id: UUID, document_id: int) -> list[int] | None:
        with self._connect() as conn:  # one transaction: the ids read and the delete agree
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id "
                    "WHERE d.id = %s AND d.owner_id = %s",
                    (document_id, owner_id),
                )
            ]
            # The chunks go with it: chunks.document_id is ON DELETE CASCADE.
            row = conn.execute(
                "DELETE FROM documents WHERE id = %s AND owner_id = %s RETURNING id",
                (document_id, owner_id),
            ).fetchone()
        return None if row is None else ids

    def owned_chunk_ids(self, owner_id: UUID) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM chunks WHERE owner_id = %s", (owner_id,)).fetchall()
        return [r[0] for r in rows]

    def index_rows(self) -> list[IndexRow]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id, owner_id, heading, content FROM chunks").fetchall()
        return [IndexRow(*row) for row in rows]

    def log_event(self, name: str, user_id: UUID | None, props: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (user_id, name, props) VALUES (%s, %s, %s)",
                (user_id, name, Jsonb(props)),
            )

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

    def event_stats(self, days: int = STATS_DAYS) -> dict:
        """Totals per event name, distinct users, the last `days` days (UTC) per day, the
        main-action rate and the LLM cost per active user. Missing days and names are zeros."""
        today = datetime.now(UTC).date()
        first = today - timedelta(days=days - 1)
        with self._connect() as conn:
            totals = dict(conn.execute("SELECT name, count(*) FROM events GROUP BY name"))
            (distinct_users,) = conn.execute(
                "SELECT count(DISTINCT user_id) FROM events"
            ).fetchone()
            (registered,) = conn.execute("SELECT count(*) FROM users").fetchone()
            daily = conn.execute(
                "SELECT (created_at AT TIME ZONE 'UTC')::date, name, count(*) FROM events "
                "WHERE created_at >= %s GROUP BY 1, 2",
                (datetime(first.year, first.month, first.day, tzinfo=UTC),),
            ).fetchall()
            by_channel = {
                (channel, name): n
                for channel, name, n in conn.execute(
                    "SELECT COALESCE(props->>'channel', 'web'), name, count(*) FROM events "
                    "GROUP BY 1, 2"
                )
            }
            channel_users = dict(
                conn.execute(
                    "SELECT COALESCE(props->>'channel', 'web'), count(DISTINCT user_id) "
                    "FROM events GROUP BY 1"
                ).fetchall()
            )
            (cited_users,) = conn.execute(
                "SELECT count(DISTINCT user_id) FROM events "
                "WHERE name = 'question_answered' AND props->>'cited' = 'true'"
            ).fetchone()
            (active_users,) = conn.execute(
                "SELECT count(DISTINCT user_id) FROM events WHERE name = 'question_answered'"
            ).fetchone()
            cost, calls = conn.execute(
                "SELECT COALESCE(sum(cost_usd), 0)::float8, count(*) FROM llm_calls"
            ).fetchone()
        per_day: dict = {}
        for day, name, n in daily:
            per_day.setdefault(day, {})[name] = n
        return assemble_stats(
            totals,
            distinct_users,
            registered,
            per_day,
            cited_users,
            active_users,
            cost,
            calls,
            today,
            days,
            by_channel,
            channel_users,
        )


def assemble_stats(
    totals: dict[str, int],
    distinct_users: int,
    registered: int,
    per_day: dict,
    cited_users: int,
    active_users: int,
    cost: float,
    calls: int,
    today,
    days: int,
    by_channel: dict[tuple[str, str], int] | None = None,
    channel_users: dict[str, int] | None = None,
) -> dict:
    """The one place that shapes the numbers, shared by PgStore and the in-memory test store.

    Main-action rate = registered users who got at least one CITED answer / registered users.
    `by_channel` is {(channel, event name): count}; an event without a `channel` prop is "web"."""
    names = ("signup", "question_answered", "cards_made", "search")
    last_days = []
    for back in range(days - 1, -1, -1):
        day = today - timedelta(days=back)
        counts = per_day.get(day, {})
        last_days.append({"date": day.isoformat(), **{n: counts.get(n, 0) for n in names}})
    by_channel = by_channel or {}
    channel_users = channel_users or {}
    channels = {
        c: {**{n: by_channel.get((c, n), 0) for n in names}, "users": channel_users.get(c, 0)}
        for c in CHANNELS
    }
    return {
        "totals": {n: totals.get(n, 0) for n in names},
        "by_channel": channels,
        "distinct_users": distinct_users,
        "registered_users": registered,
        "last_days": last_days,
        "main_action": {
            "event": "question_answered",
            "definition": "a user got at least one cited answer",
            "users": cited_users,
            "rate": round(cited_users / registered, 3) if registered else 0.0,
        },
        "llm_cost": {
            "total_usd": round(cost, 6),
            "calls": calls,
            "active_users": active_users,
            "avg_per_active_user_usd": round(cost / active_users, 6) if active_users else 0.0,
        },
    }


@lru_cache
def get_store() -> Store:
    return PgStore(get_settings().database_url)
