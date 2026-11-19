from collections.abc import AsyncIterator

from mnemonic.retrieval import Hit
from mnemonic.schemas import Message


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

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self.answer
