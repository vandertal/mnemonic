from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from mnemonic.retrieval import Hit
from mnemonic.schemas import Message
from mnemonic.store import (
    Chunk,
    EmailTaken,
    LLMCall,
    StoredDocument,
    StoredMessage,
    TooManyDocuments,
    User,
)

KEY = "test-key"
AUTH = {"X-API-Key": KEY}


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
        self.messages: dict[UUID, list[StoredMessage]] = {}
        self.llm_calls: list[LLMCall] = []
        self.chunks: dict[int, Chunk] = {}
        self.chunk_owner: dict[int, UUID | None] = {}  # absent / None = shared
        self.documents: dict[int, tuple[UUID, StoredDocument]] = {}
        self.chunk_document: dict[int, int] = {}
        self.users: dict[UUID, tuple[User, str]] = {}
        self._next_id = 0
        self._next_chunk_id = 1000
        self._next_doc_id = 0

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

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> int:
        self._next_id += 1
        self.messages.setdefault(session_id, []).append(
            StoredMessage(role, content, sources, datetime.now(UTC), self._next_id)
        )
        return self._next_id

    def get_messages(self, session_id: UUID) -> list[StoredMessage]:
        return list(self.messages.get(session_id, []))

    def log_llm_call(self, call: LLMCall) -> None:
        self.llm_calls.append(call)

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
        doc = StoredDocument(self._next_doc_id, filename, datetime.now(UTC), len(chunks))
        self.documents[doc.id] = (owner_id, doc)
        for c in chunks:
            self._next_chunk_id += 1
            self.chunks[self._next_chunk_id] = Chunk(
                self._next_chunk_id, c.file_path, c.heading, c.content
            )
            self.chunk_owner[self._next_chunk_id] = owner_id
            self.chunk_document[self._next_chunk_id] = doc.id
        return doc

    def delete_document(self, owner_id: UUID, document_id: int) -> bool:
        entry = self.documents.get(document_id)
        if entry is None or entry[0] != owner_id:
            return False
        del self.documents[document_id]
        for cid in [c for c, d in self.chunk_document.items() if d == document_id]:
            del self.chunks[cid], self.chunk_owner[cid], self.chunk_document[cid]
        return True
