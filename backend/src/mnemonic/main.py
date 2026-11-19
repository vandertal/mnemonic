import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from uuid import UUID

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, StreamingResponse

from mnemonic.config import Settings, get_settings
from mnemonic.documents import DocumentError, extract_text, safe_filename
from mnemonic.ingest.chunker import Chunk as NewChunk
from mnemonic.ingest.chunker import Tokenizer, chunk_markdown
from mnemonic.ingest.embedder import embed_documents, get_tokenizer
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.llm.base import InvalidLLMOutput, LLMProvider, Usage
from mnemonic.llm.factory import build_provider, describe_provider, model_name
from mnemonic.llm.retry import call_with_retry, stream_with_retry
from mnemonic.rag import (
    REFUSAL,
    build_flashcard_messages,
    build_messages,
    check_source_ids,
    select_history,
    valid_citations,
)
from mnemonic.retrieval import Hit, PgRetriever, Retriever
from mnemonic.schemas import (
    ChatRequest,
    ClientMessage,
    FlashcardRequest,
    FlashcardSet,
    Message,
)
from mnemonic.security import (
    get_global_limiter,
    limit_per_ip,
    require_api_key,
    spend_llm_budget,
)
from mnemonic.store import LLMCall, PgStore, Store, StoredDocument, TooManyDocuments

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


# Real models in production; tests override both, so they never load a model or touch the network.
@lru_cache
def get_embedder() -> Callable[[list[str]], Sequence[np.ndarray]]:
    return embed_documents


@lru_cache
def get_chunk_tokenizer() -> Callable[[], Tokenizer]:
    return get_tokenizer


def sse(data: object, event: str | None = None) -> str:
    """Format one Server-Sent Event. Data is JSON so newlines in tokens stay safe."""
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data)}\n\n"


async def save_message(
    store: Store, session_id: UUID, role: str, content: str, sources: list[dict] | None = None
) -> int:
    return await asyncio.to_thread(store.add_message, session_id, role, content, sources)


async def refusal_stream(store: Store, session_id: UUID) -> AsyncIterator[str]:
    yield sse(REFUSAL)
    message_id = await save_message(store, session_id, "assistant", REFUSAL, [])
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
    message_id: int | None = None
    try:
        message_id = await save_message(store, session_id, "assistant", "".join(answer), sources)
    except Exception:
        # The user already has the answer on screen; losing history is the lesser evil.
        logger.exception("could not save the assistant message")
    yield sse(sources, event="sources")
    yield sse({"message_id": message_id}, event="done")  # None if saving failed


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
    hits = await asyncio.to_thread(retriever, request.message, request.owner_id)
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
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": m.sources,
            "created_at": m.created_at,
        }
        for m in stored
    ]


# Non-streaming: the whole call may include retries (429/503 backoff) and one repeat on invalid
# JSON, so it gets a few single-call timeouts, not one.
FLASHCARDS_TIMEOUT_FACTOR = 3


@app.post("/flashcards", dependencies=[Depends(require_api_key), Depends(limit_per_ip)])
async def flashcards(
    request: FlashcardRequest,
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
    global_limiter: Annotated[SlidingWindowLimiter, Depends(get_global_limiter)],
) -> FlashcardSet:
    """3-5 flashcards from one stored assistant answer and the chunks it cited."""
    stored = await asyncio.to_thread(store.get_messages, request.session_id)
    message = next(
        (m for m in stored if m.id == request.message_id and m.role == "assistant"), None
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Answer not found in this session")
    source_ids = [s["id"] for s in message.sources or [] if isinstance(s.get("id"), int)]
    # Chunks come from the DB by the ids saved with the answer: the client sends no text.
    chunks = (
        await asyncio.to_thread(store.get_chunks, source_ids, request.owner_id)
        if source_ids
        else []
    )
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
        request.session_id,
        messages,
        cards.model_dump_json() if cards else "",
        usage,
        retries,
        round((time.perf_counter() - started) * 1000),
        ok=cards is not None,
    )
    if cards is None:
        raise HTTPException(status_code=502, detail=detail)
    return check_source_ids(cards, {c.id for c in chunks})


@app.get("/chunks/{chunk_id}", dependencies=[Depends(require_api_key)])
async def chunk_text(
    chunk_id: Annotated[int, PathParam(ge=1, le=2**63 - 1)],  # chunks.id is a Postgres bigint
    store: Annotated[Store, Depends(get_store)],
    owner_id: UUID | None = None,
) -> dict:
    """The text behind a citation. Behind the key like everything else (the corpus is public,
    but this endpoint must not become a free scraper). Someone else's uploaded chunk answers
    404, exactly like a missing one: ids must not be enumerable."""
    found = await asyncio.to_thread(store.get_chunks, [chunk_id], owner_id)
    if not found:
        raise HTTPException(status_code=404, detail="Chunk not found")
    c = found[0]
    return {"id": c.id, "file": c.file_path, "heading": c.heading, "content": c.content}


def document_json(d: StoredDocument) -> dict:
    return {"id": d.id, "filename": d.filename, "chunks": d.chunks, "created_at": d.created_at}


@app.post(
    "/documents",
    status_code=201,
    dependencies=[Depends(require_api_key), Depends(limit_per_ip)],
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    owner_id: Annotated[UUID, Form()],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
    embedder: Annotated[Callable[[list[str]], Sequence[np.ndarray]], Depends(get_embedder)],
    tokenizer: Annotated[Callable[[], Tokenizer], Depends(get_chunk_tokenizer)],
) -> dict:
    """Upload a .md / .txt / .pdf into the caller's own space (see ChatRequest.owner_id)."""
    limit = settings.max_upload_bytes
    # A cheap early "no" from the header (the body of a multipart request carries a little
    # overhead); the real check is on the bytes below.
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit + 64 * 1024:
        raise HTTPException(status_code=413, detail=f"The file is larger than {limit // 2**20} MB")
    name = safe_filename(file.filename)
    try:
        if await asyncio.to_thread(store.count_documents, owner_id) >= (
            settings.max_documents_per_owner
        ):
            raise TooManyDocuments
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise DocumentError(413, f"The file is larger than {limit // 2**20} MB")

        def prepare() -> tuple[list[NewChunk], Sequence[np.ndarray]]:
            # pypdf, tokenizing and embedding are CPU-bound: this runs in a worker thread.
            text = extract_text(name, data, settings.max_pdf_pages)
            chunks = chunk_markdown(text, name, tokenizer())
            if not chunks:
                raise DocumentError(422, "The file has no text")
            return chunks, embedder([c.content for c in chunks])

        chunks, vectors = await asyncio.to_thread(prepare)
        doc = await asyncio.to_thread(
            store.add_document, owner_id, name, chunks, vectors, settings.max_documents_per_owner
        )
    except DocumentError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None
    except TooManyDocuments:
        raise HTTPException(
            status_code=409,
            detail=f"You can keep at most {settings.max_documents_per_owner} documents. "
            "Delete one first.",
        ) from None
    return document_json(doc)


@app.get("/documents", dependencies=[Depends(require_api_key)])
async def list_documents(owner_id: UUID, store: Annotated[Store, Depends(get_store)]) -> list[dict]:
    return [document_json(d) for d in await asyncio.to_thread(store.list_documents, owner_id)]


@app.delete("/documents/{document_id}", status_code=204, dependencies=[Depends(require_api_key)])
async def delete_document(
    document_id: Annotated[int, PathParam(ge=1, le=2**63 - 1)],
    owner_id: UUID,
    store: Annotated[Store, Depends(get_store)],
) -> Response:
    """Only the owner's own documents; someone else's is a plain 404."""
    if not await asyncio.to_thread(store.delete_document, owner_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(status_code=204)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
