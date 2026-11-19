from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from mnemonic.retrieval import Hit
from mnemonic.schemas import Message
from mnemonic.store import LLMCall, StoredMessage

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

    def __call__(self, question: str) -> list[Hit]:
        self.questions.append(question)
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
        self.schema_initialized = False

    def init_schema(self) -> None:
        self.schema_initialized = True

    def add_message(
        self, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
    ) -> None:
        self.messages.setdefault(session_id, []).append(
            StoredMessage(role, content, sources, datetime.now(UTC))
        )

    def get_messages(self, session_id: UUID) -> list[StoredMessage]:
        return list(self.messages.get(session_id, []))

    def log_llm_call(self, call: LLMCall) -> None:
        self.llm_calls.append(call)
