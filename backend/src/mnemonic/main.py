import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, StreamingResponse

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm.base import LLMProvider, Usage
from mnemonic.llm.factory import build_provider, describe_provider, model_name
from mnemonic.llm.retry import stream_with_retry
from mnemonic.rag import REFUSAL, build_messages, select_history, valid_citations
from mnemonic.retrieval import Hit, PgRetriever, Retriever
from mnemonic.schemas import ChatRequest, ClientMessage, Message
from mnemonic.security import (
    get_global_limiter,
    limit_per_ip,
    require_api_key,
    spend_llm_budget,
)
from mnemonic.store import LLMCall, PgStore, Store

# uvicorn configures only its own loggers; without this our INFO lines would be dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolved through dependency_overrides like the store below, so tests control the settings.
    settings = app.dependency_overrides.get(get_settings, get_settings)()
    if not settings.app_api_key:
        raise RuntimeError("APP_API_KEY is not set (see backend/.env.example)")
    logger.info("LLM provider: %s", describe_provider(settings))
    store = app.dependency_overrides.get(get_store, get_store)()
    await asyncio.to_thread(store.init_schema)
    yield


app = FastAPI(title="Mnemonic", lifespan=lifespan)


@lru_cache
def get_store() -> Store:
    return PgStore(get_settings().database_url)


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())


@lru_cache
def get_retriever() -> Retriever:
    settings = get_settings()
    return PgRetriever(settings.database_url, settings.retrieval_top_k)


def sse(data: object, event: str | None = None) -> str:
    """Format one Server-Sent Event. Data is JSON so newlines in tokens stay safe."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data)}\n\n"


async def save_message(
    store: Store, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
) -> None:
    await asyncio.to_thread(store.add_message, session_id, role, content, sources)


async def refusal_stream(store: Store, session_id: UUID) -> AsyncIterator[str]:
    yield sse(REFUSAL)
    await save_message(store, session_id, "assistant", REFUSAL, [])
    yield sse("", event="done")


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


async def event_stream(
    provider: LLMProvider,
    messages: list[Message],
    hits: list[Hit],
    settings: Settings,
    store: Store,
    session_id: UUID,
) -> AsyncIterator[str]:
    timeout = settings.llm_timeout_seconds
    usage, retries = Usage(), 0

    def count_retry() -> None:
        nonlocal retries
        retries += 1

    # By the time a token fails, HTTP 200 is already sent — report errors as an event.
    tokens = stream_with_retry(provider, messages, usage, on_retry=count_retry)
    answer: list[str] = []
    error: str | None = None
    started = time.perf_counter()
    try:
        while True:
            # Idle timeout: applies to every wait, so a model that never starts
            # (or stalls mid-answer) cannot hang the request forever.
            async with asyncio.timeout(timeout):
                try:
                    token = await anext(tokens)
                except StopAsyncIteration:
                    break
            answer.append(token)
            yield sse(token)
    except TimeoutError:
        logger.warning("LLM provider sent nothing for %.1fs, giving up", timeout)
        error = (
            f"The model did not respond within {timeout:g} seconds. "
            "It may be overloaded — please try again."
        )
    except Exception:
        logger.exception("LLM provider failed mid-stream")
        error = "The model failed to answer. Please try again."
    finally:
        # Stop the provider's generator so its HTTP request is closed too.
        await tokens.aclose()
    # Not reached when the client disconnects (the generator is closed at a `yield`): such
    # calls are not logged.
    await log_llm_call(
        store,
        settings,
        session_id,
        messages,
        "".join(answer),
        usage,
        retries,
        round((time.perf_counter() - started) * 1000),
        ok=error is None,
    )
    if error:
        yield sse(error, event="error")
        return
    # Only citations that point to really retrieved chunks reach the client.
    sources = [
        {"id": h.id, "file_path": h.file_path, "heading": h.heading, "similarity": h.similarity}
        for h in valid_citations("".join(answer), hits)
    ]
    try:
        await save_message(store, session_id, "assistant", "".join(answer), sources)
    except Exception:
        # The user already has the answer on screen; losing history is the lesser evil.
        logger.exception("could not save the assistant message")
    yield sse(sources, event="sources")
    yield sse("", event="done")


# Order matters: the key is checked first, so unauthenticated requests never touch the limiter.
@app.post("/chat", dependencies=[Depends(require_api_key), Depends(limit_per_ip)])
async def chat(
    request: ChatRequest,
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    store: Annotated[Store, Depends(get_store)],
    global_limiter: Annotated[SlidingWindowLimiter, Depends(get_global_limiter)],
) -> StreamingResponse:
    # Embedding + DB query are blocking: keep them off the event loop.
    hits = await asyncio.to_thread(retriever, request.message)
    best = hits[0].similarity if hits else 0.0
    logger.info("retrieval: %d hits, top similarity %.3f", len(hits), best)

    refuse = not hits or best < settings.similarity_threshold
    if not refuse:
        # Only a real LLM call spends the service-wide budget: "I don't know" is free.
        # Raised before anything is saved or streamed, so the client can simply retry.
        spend_llm_budget(global_limiter)
    # History is read BEFORE the current question is saved, so it never contains it.
    stored = await asyncio.to_thread(store.get_messages, request.session_id)
    history = select_history(stored, settings.history_messages)
    # Saved only now, when the request is going to be answered (or refused) for sure.
    await save_message(store, request.session_id, "user", request.message)
    if refuse:
        body = refusal_stream(store, request.session_id)  # no LLM call: nothing relevant found
    else:
        # Retrieval used only the current question; the model also sees the recent turns.
        current = ClientMessage(role="user", content=request.message)
        messages = build_messages([*history, current], hits)
        body = event_stream(provider, messages, hits, settings, store, request.session_id)
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions/{session_id}/messages", dependencies=[Depends(require_api_key)])
async def session_messages(
    session_id: UUID, store: Annotated[Store, Depends(get_store)]
) -> list[dict]:
    """Chat history, oldest first. An unknown session is just an empty history."""
    stored = await asyncio.to_thread(store.get_messages, session_id)
    return [
        {"role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at}
        for m in stored
    ]


@app.get("/chunks/{chunk_id}", dependencies=[Depends(require_api_key)])
async def chunk_text(
    chunk_id: Annotated[int, PathParam(ge=1, le=2**63 - 1)],  # chunks.id is a Postgres bigint
    store: Annotated[Store, Depends(get_store)],
) -> dict:
    """The text behind a citation. Behind the key like everything else (the corpus is public,
    but this endpoint must not become a free scraper)."""
    found = await asyncio.to_thread(store.get_chunks, [chunk_id])
    if not found:
        raise HTTPException(status_code=404, detail="Chunk not found")
    c = found[0]
    return {"id": c.id, "file": c.file_path, "heading": c.heading, "content": c.content}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
