import threading
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from mnemonic.auth import create_access_token
from mnemonic.config import Settings
from mnemonic.retrieval import Hit
from mnemonic.schemas import Message
from mnemonic.store import (
    DEFAULT_TITLE,
    Chunk,
    EmailTaken,
    IndexRow,
    LLMCall,
    Session,
    SessionNotFound,
    StoredDocument,
    StoredMessage,
    TooManyDocuments,
    User,
    assemble_stats,
    first_line_title,
    telegram_email,
)


def make_hit(id: int, similarity: float = 0.9) -> Hit:
    return Hit(
        id=id,
        similarity=similarity,
        file_path=f"tutorial/page-{id}.md",
        heading=f"Heading {id}",
        content=f"Content of chunk {id}.",
    )


class FakeRetriever:
    """Returns fixed hits and records the questions it was asked. No DB, no embeddings."""

    def __init__(self, hits: list[Hit]) -> None:
        self.hits = hits
        self.questions: list[str] = []
        self.owners: list[UUID | None] = []

    def __call__(self, question: str, owner_id: UUID | None = None) -> list[Hit]:
        self.questions.append(question)
        self.owners.append(owner_id)
        return self.hits


class RecordingProvider:
    """Streams a fixed answer and records the messages it received (to detect calls)."""

    def __init__(self, answer: str = "ok") -> None:
        self.answer = answer
        self.calls: list[list[Message]] = []

    async def stream(self, messages: list[Message], usage=None) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self.answer


class MemoryStore:
    """In-memory Store: records messages and LLM calls. No database."""

    def __init__(self) -> None:
        self.sessions: dict[UUID, tuple[UUID, Session]] = {}  # id -> (owner, session)
        self.messages: dict[UUID, list[StoredMessage]] = {}
        self.llm_calls: list[LLMCall] = []
        self.chunks: dict[int, Chunk] = {}
        self.chunk_owner: dict[int, UUID | None] = {}  # absent / None = shared
        self.documents: dict[int, tuple[UUID, StoredDocument]] = {}
        self.chunk_document: dict[int, int] = {}
        self.users: dict[UUID, tuple[User, str]] = {}
        self.telegram: dict[int, UUID] = {}  # telegram_id -> user id
        self._telegram_lock = threading.Lock()
        self.events: list[tuple[str, UUID | None, dict, datetime]] = []
        self.fail_events = False  # a test switch: log_event raises like a broken database
        self._next_id = 0
        self._next_chunk_id = 1000
        self._next_doc_id = 0
        self._ticks = 0

    def create_user(self, email: str, password_hash: str) -> User:
        if any(u.email == email for u, _ in self.users.values()):
            raise EmailTaken
        user = User(uuid4(), email, datetime.now(UTC))
        self.users[user.id] = (user, password_hash)
        return user

    def get_user_by_email(self, email: str) -> tuple[User, str] | None:
        return next(((u, h) for u, h in self.users.values() if u.email == email), None)

    def get_user(self, user_id: UUID) -> User | None:
        entry = self.users.get(user_id)
        return entry[0] if entry else None

    def find_telegram_user(self, telegram_id: int) -> User | None:
        uid = self.telegram.get(telegram_id)
        return self.users[uid][0] if uid else None

    def get_or_create_telegram_user(
        self, telegram_id: int, password_hash: str
    ) -> tuple[User, bool]:
        with self._telegram_lock:  # the real store serialises with an advisory lock
            found = self.find_telegram_user(telegram_id)
            if found:
                return found, False
            user = self.create_user(telegram_email(telegram_id), password_hash)
            self.telegram[telegram_id] = user.id
            return user, True

    def _now(self) -> datetime:
        """A strictly increasing fake clock, so 'newest first' is never a tie."""
        self._ticks += 1
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self._ticks)

    def delete_user(self, user_id: UUID) -> bool:
        if self.users.pop(user_id, None) is None:
            return False
        self.telegram = {t: u for t, u in self.telegram.items() if u != user_id}  # cascade
        for sid in [i for i, (owner, _) in self.sessions.items() if owner == user_id]:
            self.delete_session(user_id, sid)
        for did in [i for i, (owner, _) in self.documents.items() if owner == user_id]:
            self.delete_document(user_id, did)
        return True

    def seed_session(self, user_id: UUID, session_id: UUID, title: str = DEFAULT_TITLE) -> Session:
        """Test helper: a session with a chosen id (the real store always generates it)."""
        now = self._now()
        session = Session(session_id, title, now, now)
        self.sessions[session_id] = (user_id, session)
        return session

    def create_session(self, user_id: UUID, title: str | None = None) -> Session:
        return self.seed_session(user_id, uuid4(), title or DEFAULT_TITLE)

    def list_sessions(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Session], int]:
        mine = sorted(
            (s for owner, s in self.sessions.values() if owner == user_id),
            key=lambda s: (-s.updated_at.timestamp(), str(s.id)),
        )
        return mine[offset : offset + limit], len(mine)

    def get_session(self, user_id: UUID, session_id: UUID) -> Session | None:
        entry = self.sessions.get(session_id)
        return entry[1] if entry and entry[0] == user_id else None

    def rename_session(self, user_id: UUID, session_id: UUID, title: str) -> Session | None:
        session = self.get_session(user_id, session_id)
        if session is None:
            return None
        renamed = Session(session.id, title, session.created_at, session.updated_at)
        self.sessions[session_id] = (user_id, renamed)
        return renamed

    def delete_session(self, user_id: UUID, session_id: UUID) -> bool:
        if self.get_session(user_id, session_id) is None:
            return False
        del self.sessions[session_id]
        self.messages.pop(session_id, None)
        self.llm_calls = [c for c in self.llm_calls if c.session_id != session_id]
        return True

    def add_message(
        self,
        user_id: UUID,
        session_id: UUID,
        role: str,
        content: str,
        sources: list[dict] | None = None,
    ) -> int:
        session = self.get_session(user_id, session_id)
        if session is None:
            raise SessionNotFound
        title = session.title
        if title == DEFAULT_TITLE and role == "user" and first_line_title(content):
            title = first_line_title(content)
        self.sessions[session_id] = (
            user_id,
            Session(session.id, title, session.created_at, self._now()),
        )
        self._next_id += 1
        self.messages.setdefault(session_id, []).append(
            StoredMessage(role, content, sources, datetime.now(UTC), self._next_id)
        )
        return self._next_id

    def get_messages(self, user_id: UUID, session_id: UUID) -> list[StoredMessage] | None:
        if self.get_session(user_id, session_id) is None:
            return None
        return list(self.messages.get(session_id, []))

    def log_llm_call(self, call: LLMCall) -> None:
        self.llm_calls.append(call)

    def log_event(self, name: str, user_id: UUID | None, props: dict) -> None:
        if self.fail_events:
            raise RuntimeError("events table is down")
        self.events.append((name, user_id, props, datetime.now(UTC)))

    def event_stats(self, days: int = 7) -> dict:
        today = datetime.now(UTC).date()
        totals: dict[str, int] = {}
        per_day: dict = {}
        for name, _, _, at in self.events:
            totals[name] = totals.get(name, 0) + 1
            day = per_day.setdefault(at.date(), {})
            day[name] = day.get(name, 0) + 1
        by_channel: dict[tuple[str, str], int] = {}
        users_of: dict[str, set] = {}
        for name, uid, props, _ in self.events:
            channel = props.get("channel", "web")
            by_channel[(channel, name)] = by_channel.get((channel, name), 0) + 1
            if uid:
                users_of.setdefault(channel, set()).add(uid)
        answered = [(u, p) for n, u, p, _ in self.events if n == "question_answered"]
        cited = {u for u, p in answered if p.get("cited")}
        active = {u for u, _ in answered}
        return assemble_stats(
            totals,
            len({u for _, u, _, _ in self.events if u}),
            len(self.users),
            per_day,
            len(cited),
            len(active),
            float(sum(c.cost_usd for c in self.llm_calls)),
            len(self.llm_calls),
            today,
            days,
            by_channel,
            {c: len(u) for c, u in users_of.items()},
            _count_errors(self.llm_calls),
        )

    def get_chunks(self, ids: list[int], owner_id: UUID | None = None) -> list[Chunk]:
        return [
            self.chunks[i]
            for i in sorted(ids)
            if i in self.chunks and self.chunk_owner.get(i) in (None, owner_id)
        ]

    def count_documents(self, owner_id: UUID) -> int:
        return sum(1 for o, _ in self.documents.values() if o == owner_id)

    def list_documents(self, owner_id: UUID) -> list[StoredDocument]:
        return [d for o, d in self.documents.values() if o == owner_id]

    def add_document(self, owner_id, filename, chunks, vectors, max_documents) -> StoredDocument:
        assert len(chunks) == len(vectors)
        if self.count_documents(owner_id) >= max_documents:
            raise TooManyDocuments
        self._next_doc_id += 1
        ids = tuple(self._next_chunk_id + 1 + i for i in range(len(chunks)))
        doc = StoredDocument(self._next_doc_id, filename, datetime.now(UTC), len(chunks), ids)
        self.documents[doc.id] = (owner_id, doc)
        for c in chunks:
            self._next_chunk_id += 1
            self.chunks[self._next_chunk_id] = Chunk(
                self._next_chunk_id, c.file_path, c.heading, c.content
            )
            self.chunk_owner[self._next_chunk_id] = owner_id
            self.chunk_document[self._next_chunk_id] = doc.id
        return doc

    def delete_document(self, owner_id: UUID, document_id: int) -> list[int] | None:
        entry = self.documents.get(document_id)
        if entry is None or entry[0] != owner_id:
            return None
        del self.documents[document_id]
        ids = [c for c, d in self.chunk_document.items() if d == document_id]
        for cid in ids:
            del self.chunks[cid], self.chunk_owner[cid], self.chunk_document[cid]
        return ids

    def owned_chunk_ids(self, owner_id: UUID) -> list[int]:
        return sorted(c for c, o in self.chunk_owner.items() if o == owner_id and c in self.chunks)

    def index_rows(self) -> list[IndexRow]:
        return [
            IndexRow(c.id, self.chunk_owner.get(c.id), c.heading, c.content)
            for c in self.chunks.values()
        ]


def login(store: MemoryStore, email: str = "alice@example.com", sessions: Iterable[UUID] = ()):
    """The one way tests authenticate: get-or-create the account, give it the listed sessions
    (by id) and return the Authorization header with a real signed token."""
    found = store.get_user_by_email(email)
    user = found[0] if found else store.create_user(email, "not-a-real-hash")
    for session_id in sessions:
        if store.get_session(user.id, session_id) is None:
            store.seed_session(user.id, session_id)
    token = create_access_token(user.id, Settings(_env_file=None))
    return {"Authorization": f"Bearer {token}"}


def user_id(store: MemoryStore, email: str = "alice@example.com") -> UUID:
    return store.get_user_by_email(email)[0].id


def _count_errors(calls) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in calls:
        if c.error_class:
            out[c.error_class] = out.get(c.error_class, 0) + 1
    return out
