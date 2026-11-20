import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from mnemonic.schemas import Message, ToolCall, ToolSpec

logger = logging.getLogger(__name__)


# One retry on invalid JSON: models sometimes break the format once, rarely twice in a row.
JSON_ATTEMPTS = 2


@dataclass
class Usage:
    """Token counts of one LLM call. The caller creates it, the provider fills it in while
    streaming (a per-call object, so a provider shared between requests stays safe).
    None = the provider did not report it."""

    tokens_in: int | None = None
    tokens_out: int | None = None


class InvalidLLMOutput(Exception):
    """The model kept returning JSON that does not match the schema."""


class LLMProvider(Protocol):
    """Anything that can turn a conversation into a stream of text tokens, or into an object."""

    # Providers that can call tools set this to True and implement stream_events; for the
    # others the server never offers tools. Read it with getattr(provider, "supports_tools", False).
    supports_tools: bool

    def stream(self, messages: list[Message], usage: Usage | None = None) -> AsyncIterator[str]: ...

    def stream_events(
        self, messages: list[Message], tools: list[ToolSpec], usage: Usage | None = None
    ) -> AsyncIterator[str | ToolCall]:
        """Like stream(), but may also yield a ToolCall (only if supports_tools)."""
        ...

    async def generate_json[T: BaseModel](
        self, messages: list[Message], schema: type[T], usage: Usage | None = None
    ) -> T:
        """Structured output: an instance of `schema`, or InvalidLLMOutput after 2 bad tries."""
        ...


async def parse_json_with_retry[T: BaseModel](
    complete: Callable[[], Awaitable[str]], schema: type[T]
) -> T:
    """Call `complete` (returns raw JSON text) until it validates against `schema`.

    Shared by all providers, so "what is valid" and "how often we retry" live in one place."""
    for attempt in range(1, JSON_ATTEMPTS + 1):
        raw = await complete()
        try:
            return schema.model_validate_json(raw)
        except ValidationError as exc:
            logger.warning(
                "LLM returned invalid JSON (attempt %d/%d): %s", attempt, JSON_ATTEMPTS, exc
            )
    raise InvalidLLMOutput(f"The model did not return valid {schema.__name__} JSON")
