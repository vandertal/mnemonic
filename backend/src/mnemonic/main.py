import asyncio
import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from mnemonic.config import Settings, get_settings
from mnemonic.llm.base import LLMProvider
from mnemonic.llm.factory import build_provider
from mnemonic.rag import REFUSAL, build_messages, valid_citations
from mnemonic.retrieval import Hit, PgRetriever, Retriever
from mnemonic.schemas import ChatRequest, Message

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mnemonic")


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


async def refusal_stream() -> AsyncIterator[str]:
    yield sse(REFUSAL)
    yield sse("", event="done")


async def event_stream(
    provider: LLMProvider, messages: list[Message], hits: list[Hit], timeout: float
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
    yield sse(sources, event="sources")
    yield sse("", event="done")


@app.post("/chat")
async def chat(
    request: ChatRequest,
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
) -> StreamingResponse:
    # Embedding + DB query are blocking: keep them off the event loop.
    hits = await asyncio.to_thread(retriever, request.messages[-1].content)
    best = hits[0].similarity if hits else 0.0
    logger.info("retrieval: %d hits, top similarity %.3f", len(hits), best)

    if not hits or best < settings.similarity_threshold:
        body = refusal_stream()  # no LLM call: nothing relevant was found
    else:
        messages = build_messages(request.messages, hits)
        body = event_stream(provider, messages, hits, settings.llm_timeout_seconds)
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
