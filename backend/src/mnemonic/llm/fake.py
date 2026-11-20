import asyncio
from collections.abc import AsyncIterator

from pydantic import BaseModel

from mnemonic.llm.base import Usage, parse_json_with_retry
from mnemonic.schemas import FlashcardSet, Message, ToolCall, ToolSpec

_DEFAULT_CARDS = FlashcardSet.model_validate(
    {
        "cards": [
            {
                "question": f"Fake question {i}?",
                "answer": f"Fake answer {i}.",
                "source_chunk_id": None,
            }
            for i in (1, 2, 3)
        ]
    }
)


class FakeProvider:
    """Echoes the last user message word by word. For tests and keyless local runs.

    generate_json returns `json_responses` one by one (raw text, so a test can script invalid
    JSON); without them it returns a fixed valid FlashcardSet.

    `tool_script` makes it a tool-calling provider (supports_tools=True): one list of events
    (text tokens or ToolCall) per stream_events() call, in order; when the script runs out it
    echoes. Every stream_events() call is recorded in `event_calls` as (messages, tools)."""

    def __init__(
        self,
        delay: float = 0.0,
        json_responses: list[str] | None = None,
        tool_script: list[list[str | ToolCall]] | None = None,
    ) -> None:
        self._delay = delay
        self._json_responses = list(json_responses or [])
        self.json_calls = 0
        self.supports_tools = tool_script is not None
        self._tool_script = list(tool_script or [])
        self.event_calls: list[tuple[list[Message], list[ToolSpec]]] = []

    async def stream_events(
        self, messages: list[Message], tools: list[ToolSpec], usage: Usage | None = None
    ) -> AsyncIterator[str | ToolCall]:
        self.event_calls.append((list(messages), list(tools)))
        if not self._tool_script:
            async for token in self.stream(messages, usage):
                yield token
            return
        for event in self._tool_script.pop(0):
            yield event

    async def stream(
        self, messages: list[Message], usage: Usage | None = None
    ) -> AsyncIterator[str]:
        last = messages[-1].content
        for word in f"Echo: {last}".split(" "):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield word + " "

    async def generate_json[T: BaseModel](
        self, messages: list[Message], schema: type[T], usage: Usage | None = None
    ) -> T:
        async def complete() -> str:
            self.json_calls += 1
            if self._json_responses:
                return self._json_responses.pop(0)
            return _DEFAULT_CARDS.model_dump_json()

        return await parse_json_with_retry(complete, schema)
