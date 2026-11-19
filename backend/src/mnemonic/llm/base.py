from collections.abc import AsyncIterator
from typing import Protocol

from mnemonic.schemas import Message


class LLMProvider(Protocol):
    """Anything that can turn a conversation into a stream of text tokens."""

    def stream(self, messages: list[Message]) -> AsyncIterator[str]: ...
