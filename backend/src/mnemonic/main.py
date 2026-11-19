import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from mnemonic.config import Settings, get_settings
from mnemonic.llm.base import LLMProvider
from mnemonic.llm.factory import build_provider, describe_provider
from mnemonic.rag import REFUSAL, build_messages, valid_citations
from mnemonic.retrieval import Hit, PgRetriever, Retriever
from mnemonic.schemas import ChatRequest, ClientMessage, Message
from mnemonic.store import PgStore, Store

# uvicorn configures only its own loggers; without this our INFO lines would be dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("LLM provider: %s", describe_provider(get_settings()))
    # Resolve through dependency_overrides so tests can swap the store without a database.
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


async def event_stream(
    provider: LLMProvider,
    messages: list[Message],
    hits: list[Hit],
    timeout: float,
    store: Store,
    session_id: UUID,
) -> AsyncIterator[str]:
    # By the time a token fails, HTTP 200 is already sent — report errors as an event.
    tokens = provider.stream(messages)
    answer: list[str] = []
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
        yield sse(
            f"The model did not respond within {timeout:g} seconds. "
            "It may be overloaded — please try again.",
            event="error",
        )
        return
    except Exception:
        logger.exception("LLM provider failed mid-stream")
        yield sse("The model failed to answer. Please try again.", event="error")
        return
    finally:
        # Stop the provider's generator so its HTTP request is closed too.
        aclose = getattr(tokens, "aclose", None)
        if aclose:
            await aclose()
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


@app.post("/chat")
async def chat(
    request: ChatRequest,
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    store: Annotated[Store, Depends(get_store)],
) -> StreamingResponse:
    # Embedding + DB query are blocking: keep them off the event loop.
    hits = await asyncio.to_thread(retriever, request.message)
    best = hits[0].similarity if hits else 0.0
    logger.info("retrieval: %d hits, top similarity %.3f", len(hits), best)

    refuse = not hits or best < settings.similarity_threshold
    # Saved only now, when the request is going to be answered (or refused) for sure.
    await save_message(store, request.session_id, "user", request.message)
    if refuse:
        body = refusal_stream(store, request.session_id)  # no LLM call: nothing relevant found
    else:
        # For now the model sees only the current question; conversation memory is M6.
        messages = build_messages([ClientMessage(role="user", content=request.message)], hits)
        body = event_stream(
            provider, messages, hits, settings.llm_timeout_seconds, store, request.session_id
        )
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: UUID, store: Annotated[Store, Depends(get_store)]
) -> list[dict]:
    """Chat history, oldest first. An unknown session is just an empty history."""
    stored = await asyncio.to_thread(store.get_messages, session_id)
    return [
        {"role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at}
        for m in stored
    ]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
