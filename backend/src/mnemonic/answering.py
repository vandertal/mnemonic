"""The answering core shared by every client (the web routes and the Telegram bot).

`start_answer` is everything `POST /chat` does between "the session is the caller's" and "here is
the body to stream"; `make_flashcards` is everything `POST /flashcards` does after the request
is parsed. The routes and the bot call these, so there is exactly one RAG path, one rate budget
and one place that writes `llm_calls` and events. Both raise `HTTPException` like the routes do:
a client maps the status code to its own wording.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException

from mnemonic import events as metrics
from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm.base import InvalidLLMOutput, LLMProvider, Usage
from mnemonic.llm.factory import build_provider, model_name
from mnemonic.llm.retry import call_with_retry, stream_with_retry
from mnemonic.rag import (
    REFUSAL,
    build_flashcard_messages,
    build_messages,
    check_source_ids,
    select_history,
    valid_citations,
)
from mnemonic.retrieval import Hit, PgRetriever, Retriever, is_answerable
from mnemonic.schemas import ClientMessage, FlashcardSet, Message, ToolCall
from mnemonic.search_service import get_search_service
from mnemonic.security import BUSY_MESSAGE, spend_llm_budget
from mnemonic.store import LLMCall, SessionNotFound, Store, StoredMessage
from mnemonic.tools import CALCULATOR, run_tool

logger = logging.getLogger(__name__)


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())


@lru_cache
def get_retriever() -> Retriever:
    settings = get_settings()
    return PgRetriever(
        settings.database_url,
        settings.retrieval_top_k,
        settings.retrieval_mode,
        get_search_service(),
        settings.retrieval_candidates,
    )


def sse(data: object, event: str | None = None) -> str:
    """Format one Server-Sent Event. Data is JSON so newlines in tokens stay safe."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data)}\n\n"


async def save_message(
    store: Store,
    user_id: UUID,
    session_id: UUID,
    role: str,
    content: str,
    sources: list[dict] | None = None,
) -> int:
    return await asyncio.to_thread(store.add_message, user_id, session_id, role, content, sources)


async def refusal_stream(store: Store, user_id: UUID, session_id: UUID) -> AsyncIterator[str]:
    yield sse(REFUSAL)
    message_id = await save_message(store, user_id, session_id, "assistant", REFUSAL, [])
    await metrics.emit(store, metrics.QUESTION_ANSWERED, user_id, cited=False, refused=True)
    yield sse({"message_id": message_id}, event="done")


async def log_llm_call(
    store: Store,
    settings: Settings,
    session_id: UUID,
    messages: list[Message],
    answer: str,
    usage: Usage,
    retries: int,
    latency_ms: int,
    ok: bool,
) -> None:
    """Write one row to llm_calls. Never raises: a broken log must not break the answer."""
    # Providers report real token counts; if one did not, estimate: ~4 characters per token.
    estimated = usage.tokens_in is None or usage.tokens_out is None
    tokens_in = usage.tokens_in
    if tokens_in is None:
        tokens_in = sum(len(m.content) for m in messages) // 4
    tokens_out = usage.tokens_out if usage.tokens_out is not None else len(answer) // 4
    cost = (tokens_in * settings.price_in_per_m + tokens_out * settings.price_out_per_m) / 1e6
    status = "error" if not ok else "retried" if retries else "ok"
    call = LLMCall(
        session_id=session_id,
        model=model_name(settings),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost,
        latency_ms=latency_ms,
        status=status + ("+est" if estimated else ""),
    )
    try:
        await asyncio.to_thread(store.log_llm_call, call)
    except Exception:
        logger.exception("could not write the LLM call log")


# Max LLM calls for one question: tool round(s) + the final answer. The last one gets no tools,
# so the loop always ends with text.
MAX_TOOL_ROUNDS = 3


async def event_stream(
    provider: LLMProvider,
    messages: list[Message],
    hits: list[Hit],
    settings: Settings,
    store: Store,
    user_id: UUID,
    session_id: UUID,
    global_limiter: SlidingWindowLimiter | None = None,
) -> AsyncIterator[str]:
    """Stream the answer. With a tool-calling provider this is a loop: stream; if the model asks
    for a tool, run it, append the result and stream again (max MAX_TOOL_ROUNDS rounds). Every
    round is one LLM call: one slot of the global budget and one llm_calls row. Tool calls are
    not saved in the messages table: the history keeps only the final text."""
    timeout = settings.llm_timeout_seconds
    use_tools = getattr(provider, "supports_tools", False)
    messages = list(messages)
    answer: list[str] = []
    error: str | None = None

    for round_no in range(MAX_TOOL_ROUNDS if use_tools else 1):
        if round_no:  # round 0 was paid for in chat(), before the response started
            try:
                if global_limiter:
                    spend_llm_budget(global_limiter)
            except HTTPException:  # HTTP 200 is already sent: report it as an event
                error = BUSY_MESSAGE
                break
        tools = ([CALCULATOR] if round_no < MAX_TOOL_ROUNDS - 1 else []) if use_tools else None
        usage, retries = Usage(), 0

        def count_retry() -> None:
            nonlocal retries
            retries += 1

        # By the time a token fails, HTTP 200 is already sent: report errors as an event.
        events = stream_with_retry(provider, messages, usage, on_retry=count_retry, tools=tools)
        round_text: list[str] = []
        call: ToolCall | None = None
        round_error: str | None = None
        started = time.perf_counter()
        try:
            while True:
                # Idle timeout: applies to every wait, so a model that never starts
                # (or stalls mid-answer) cannot hang the request forever.
                async with asyncio.timeout(timeout):
                    try:
                        event = await anext(events)
                    except StopAsyncIteration:
                        break
                if isinstance(event, ToolCall):
                    call = call or event  # one call per round; extra parallel ones are ignored
                    continue
                round_text.append(event)
                answer.append(event)
                yield sse(event)
        except TimeoutError:
            logger.warning("LLM provider sent nothing for %.1fs, giving up", timeout)
            round_error = (
                f"The model did not respond within {timeout:g} seconds. "
                "It may be overloaded — please try again."
            )
        except Exception:
            logger.exception("LLM provider failed mid-stream")
            round_error = "The model failed to answer. Please try again."
        finally:
            # Stop the provider's generator so its HTTP request is closed too.
            await events.aclose()
        # Not reached when the client disconnects (the generator is closed at a `yield`): such
        # calls are not logged.
        await log_llm_call(
            store,
            settings,
            session_id,
            messages,
            "".join(round_text),
            usage,
            retries,
            round((time.perf_counter() - started) * 1000),
            ok=round_error is None,
        )
        if round_error:
            error = round_error
            break
        if call is None or not tools:
            break  # a final answer (a call without offered tools is ignored)
        result = run_tool(call)
        yield sse({"name": call.name, "args": call.args, "result": result}, event="tool")
        messages += [
            Message(role="assistant", content="".join(round_text), tool_call=call),
            Message(role="tool", content=result, tool_name=call.name),
        ]

    if error:
        yield sse(error, event="error")
        return
    # Only citations that point to really retrieved chunks reach the client.
    sources = [
        {"id": h.id, "file_path": h.file_path, "heading": h.heading, "similarity": h.similarity}
        for h in valid_citations("".join(answer), hits)
    ]
    message_id: int | None = None
    try:
        message_id = await save_message(
            store, user_id, session_id, "assistant", "".join(answer), sources
        )
    except Exception:
        # The user already has the answer on screen; losing history is the lesser evil.
        logger.exception("could not save the assistant message")
    await metrics.emit(
        store, metrics.QUESTION_ANSWERED, user_id, cited=bool(sources), refused=False
    )
    yield sse(sources, event="sources")
    yield sse({"message_id": message_id}, event="done")  # None if saving failed


async def start_answer(
    *,
    provider: LLMProvider,
    settings: Settings,
    retriever: Retriever,
    store: Store,
    global_limiter: SlidingWindowLimiter,
    user_id: UUID,
    session_id: UUID,
    message: str,
) -> AsyncIterator[str]:
    """Check the session, retrieve, save the question and return the SSE body to stream.

    Raises HTTPException: 404 (not the caller's session), 429 (the service-wide LLM budget).
    Nothing is saved or streamed before those are raised, so the client can simply retry."""
    # Read before anything expensive: this is also the ownership check (None = not the caller's),
    # so a foreign session costs no embedding and no LLM call. It is read BEFORE the current
    # question is saved, so the history never contains it.
    stored = await asyncio.to_thread(store.get_messages, user_id, session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    # Embedding + DB query are blocking: keep them off the event loop.
    hits = await asyncio.to_thread(retriever, message, user_id)
    best = max((h.similarity for h in hits), default=0.0)
    logger.info("retrieval: %d hits, top similarity %.3f", len(hits), best)

    refuse = not is_answerable(hits, settings.similarity_threshold, settings.retrieval_mode)
    if not refuse:
        # Only a real LLM call spends the service-wide budget: "I don't know" is free.
        spend_llm_budget(global_limiter)
    history = select_history(stored, settings.history_messages)
    try:
        # Saved only now, when the request is going to be answered (or refused) for sure.
        await save_message(store, user_id, session_id, "user", message)
    except SessionNotFound:  # deleted between the check above and now
        raise HTTPException(status_code=404, detail="Session not found") from None
    if refuse:
        return refusal_stream(store, user_id, session_id)  # no LLM call: nothing relevant
    # Retrieval used only the current question; the model also sees the recent turns.
    current = ClientMessage(role="user", content=message)
    tools = getattr(provider, "supports_tools", False)
    messages = build_messages([*history, current], hits, tools=tools)
    return event_stream(
        provider, messages, hits, settings, store, user_id, session_id, global_limiter
    )


# Non-streaming: the whole call may include retries (429/503 backoff) and one repeat on invalid
# JSON, so it gets a few single-call timeouts, not one.
FLASHCARDS_TIMEOUT_FACTOR = 3


async def make_flashcards(
    *,
    provider: LLMProvider,
    settings: Settings,
    store: Store,
    global_limiter: SlidingWindowLimiter,
    user_id: UUID,
    session_id: UUID,
    message_id: int,
) -> FlashcardSet:
    """3-5 cards from one saved assistant answer and the chunks it cited (one LLM call).

    Raises HTTPException: 404 (session or answer not the caller's), 422 (no sources to learn
    from), 429 (budget), 502 (the model failed)."""
    stored = await asyncio.to_thread(store.get_messages, user_id, session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Session not found")
    message: StoredMessage | None = next(
        (m for m in stored if m.id == message_id and m.role == "assistant"), None
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Answer not found in this session")
    source_ids = [s["id"] for s in message.sources or [] if isinstance(s.get("id"), int)]
    # Chunks come from the DB by the ids saved with the answer: the client sends no text.
    chunks = await asyncio.to_thread(store.get_chunks, source_ids, user_id) if source_ids else []
    if not chunks:
        raise HTTPException(status_code=422, detail="This answer has no sources to learn from")

    spend_llm_budget(global_limiter)  # same service-wide budget as /chat
    messages = build_flashcard_messages(message.content, chunks)
    usage, retries = Usage(), 0

    def count_retry() -> None:
        nonlocal retries
        retries += 1

    cards: FlashcardSet | None = None
    detail = "The model failed to make flashcards. Please try again."
    started = time.perf_counter()
    try:
        async with asyncio.timeout(settings.llm_timeout_seconds * FLASHCARDS_TIMEOUT_FACTOR):
            cards = await call_with_retry(
                lambda: provider.generate_json(messages, FlashcardSet, usage),
                on_retry=count_retry,
            )
    except InvalidLLMOutput:
        detail = "The model returned flashcards in a wrong format twice. Please try again."
    except TimeoutError:
        detail = "The model did not respond in time. It may be overloaded — please try again."
    except Exception:
        logger.exception("flashcards: LLM call failed")
    await log_llm_call(
        store,
        settings,
        session_id,
        messages,
        cards.model_dump_json() if cards else "",
        usage,
        retries,
        round((time.perf_counter() - started) * 1000),
        ok=cards is not None,
    )
    if cards is None:
        raise HTTPException(status_code=502, detail=detail)
    await metrics.emit(store, metrics.CARDS_MADE, user_id)
    return check_source_ids(cards, {c.id for c in chunks})
