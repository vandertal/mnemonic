import asyncio
from collections.abc import AsyncIterator

from mnemonic.schemas import Message


class FakeProvider:
    """Echoes the last user message word by word. For tests and keyless local runs."""

    def __init__(self, delay: float = 0.0) -> None:
        self._delay = delay

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        last = messages[-1].content
        for word in f"Echo: {last}".split(" "):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield word + " "
