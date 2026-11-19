import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from mnemonic.config import get_settings
from mnemonic.llm.base import LLMProvider
from mnemonic.llm.factory import build_provider
from mnemonic.schemas import ChatRequest

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Mnemonic")


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())


def sse(data: str, event: str | None = None) -> str:
    """Format one Server-Sent Event. Data is JSON so newlines in tokens stay safe."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data)}\n\n"


async def event_stream(provider: LLMProvider, request: ChatRequest) -> AsyncIterator[str]:
    # By the time a token fails, HTTP 200 is already sent — report errors as an event.
    try:
        async for token in provider.stream(request.messages):
            yield sse(token)
    except Exception:
        logger.exception("LLM provider failed mid-stream")
        yield sse("The model failed to answer. Please try again.", event="error")
        return
    yield sse("", event="done")


@app.post("/chat")
async def chat(
    request: ChatRequest, provider: Annotated[LLMProvider, Depends(get_provider)]
) -> StreamingResponse:
    return StreamingResponse(
        event_stream(provider, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
