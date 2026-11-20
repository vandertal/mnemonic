"""Retry wrapper around LLMProvider.stream for temporary provider errors."""

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing

from mnemonic.llm.base import LLMProvider, Usage
from mnemonic.schemas import Message, ToolCall, ToolSpec

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # the first try included
BASE_DELAY = 1.0  # seconds; doubles after every failed attempt: 1, 2, 4...
RETRYABLE_STATUS = {429, 503}


async def _sleep(seconds: float) -> None:
    # A named module-level function so tests can replace it and not really wait.
    await asyncio.sleep(seconds)


def is_retryable(exc: Exception) -> bool:
    """Overload (503) or quota (429) errors. The Gemini SDK's APIError has an int `.code`
    with the HTTP status; reading it by name keeps this module free of provider imports."""
    return getattr(exc, "code", None) in RETRYABLE_STATUS


async def stream_with_retry(
    provider: LLMProvider,
    messages: list[Message],
    usage: Usage | None = None,
    on_retry: Callable[[], None] | None = None,
    tools: list[ToolSpec] | None = None,
) -> AsyncIterator[str | ToolCall]:
    """provider.stream() (stream_events() when `tools` are given), retried with exponential
    backoff + jitter, but ONLY until the first event (token or tool call) is yielded. After that
    the consumer already has part of the answer, so a retry would start the text over and
    duplicate it: the error is raised as is."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = False
        try:
            source = (
                provider.stream_events(messages, tools, usage)
                if tools is not None
                else provider.stream(messages, usage)
            )
            # aclosing: if the consumer stops early, the provider's HTTP stream is closed too.
            async with aclosing(source) as tokens:
                async for token in tokens:
                    started = True
                    yield token
            return
        except Exception as exc:
            if started or attempt == MAX_ATTEMPTS or not is_retryable(exc):
                raise
            # Jitter: clients that failed together must not all come back at the same moment.
            delay = BASE_DELAY * 2 ** (attempt - 1) + random.uniform(0, 0.5)
            logger.warning(
                "LLM call failed (%s), retry %d/%d in %.1fs",
                getattr(exc, "code", type(exc).__name__),
                attempt,
                MAX_ATTEMPTS - 1,
                delay,
            )
            if on_retry:
                on_retry()
            await _sleep(delay)


async def call_with_retry[T](
    call: Callable[[], Awaitable[T]], on_retry: Callable[[], None] | None = None
) -> T:
    """Same policy as stream_with_retry for a non-streaming call: retry 429/503 with backoff.
    There is no "first token" here: nothing is sent to the client until the call returns."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await call()
        except Exception as exc:
            if attempt == MAX_ATTEMPTS or not is_retryable(exc):
                raise
            delay = BASE_DELAY * 2 ** (attempt - 1) + random.uniform(0, 0.5)
            logger.warning(
                "LLM call failed (%s), retry %d/%d in %.1fs",
                getattr(exc, "code", type(exc).__name__),
                attempt,
                MAX_ATTEMPTS - 1,
                delay,
            )
            if on_retry:
                on_retry()
            await _sleep(delay)
    raise AssertionError("unreachable")  # the loop returns or raises
