from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from mnemonic.schemas import Message


@dataclass
class Usage:
    """Token counts of one LLM call. The caller creates it, the provider fills it in while
    streaming (a per-call object, so a provider shared between requests stays safe).
    None = the provider did not report it."""

    tokens_in: int | None = None
    tokens_out: int | None = None


class LLMProvider(Protocol):
    """Anything that can turn a conversation into a stream of text tokens."""

    def stream(self, messages: list[Message], usage: Usage | None = None) -> AsyncIterator[str]: ...
