import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from mnemonic.answering import get_provider, get_retriever, make_flashcards, start_answer
from mnemonic.auth import get_current_user
from mnemonic.config import Settings, get_settings
from mnemonic.documents import DocumentError, extract_text, safe_filename
from mnemonic.ingest.chunker import Chunk as NewChunk
from mnemonic.ingest.chunker import Tokenizer, chunk_markdown
from mnemonic.ingest.embedder import embed_documents, get_tokenizer
from mnemonic.limits import SlidingWindowLimiter, client_ip
from mnemonic.llm.base import LLMProvider
from mnemonic.llm.factory import describe_provider
from mnemonic.openapi import DESCRIPTION, R401, R404, R422, R429, TAGS
from mnemonic.retrieval import Retriever
from mnemonic.routes_admin import router as admin_router
from mnemonic.routes_auth import router as auth_router
from mnemonic.routes_search import router as search_router
from mnemonic.routes_sessions import router as sessions_router
from mnemonic.schemas import (
    ChatRequest,
    ChunkOut,
    DocumentOut,
    FlashcardRequest,
    FlashcardSet,
    HealthOut,
)
from mnemonic.search_service import (
    SearchService,
    build_from_store,
    get_search_service,
)
from mnemonic.security import (
    get_global_limiter,
    limit_per_ip,
)
from mnemonic.store import (
    IndexRow,
    Store,
    StoredDocument,
    TooManyDocuments,
    User,
    get_store,
)

# uvicorn configures only its own loggers; without this our INFO lines would be dropped.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MIN_JWT_SECRET_LENGTH = 32


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolved through dependency_overrides like the store below, so tests control the settings.
    settings = app.dependency_overrides.get(get_settings, get_settings)()
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET is not set or shorter than {MIN_JWT_SECRET_LENGTH} characters "
            "(see backend/.env.example)"
        )
    logger.info("LLM provider: %s", describe_provider(settings))
    # The index is built in a worker thread and the app starts serving at once: until it is ready
    # chat falls back to vector search and /search answers 503 (Retry-After).
    service = app.dependency_overrides.get(get_search_service, get_search_service)()
    store = app.dependency_overrides.get(get_store, get_store)()
    build = asyncio.create_task(asyncio.to_thread(build_from_store, service, store))
    try:
        yield
    finally:
        await build  # build_from_store never raises; a thread cannot be cancelled anyway


app = FastAPI(
    title="Mnemonic",
    description=DESCRIPTION,
    version="0.2.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)

# The SPA lives on another origin, so the browser sends a preflight (OPTIONS) before any request
# with an Authorization header / JSON. Only the listed origins pass; no cookies, no credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After"],  # the SPA shows a countdown from it on a 429
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Same 422 body as FastAPI's default, minus the echoed `input`: a request containing text
    that cannot be encoded (a lone surrogate) would otherwise crash the error response itself,
    and echoing user input back is not useful anyway."""
    errors = [
        {k: v for k, v in e.items() if k not in ("input", "ctx", "url")} for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(sessions_router)
app.include_router(search_router)

access_log = logging.getLogger("mnemonic.access")


# Added last = outermost, so it also sees CORS preflights and every error response.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """One JSON line per request. Only fixed, non-secret fields: no headers, no query string, no
    body, no token. `path` is the route template ("/sessions/{session_id}") when one matched, so
    ids stay out of the logs. For a streaming response (/chat) call_next returns when the response
    STARTS, so `duration_ms` is time to the first byte, not the whole answer."""
    started = time.perf_counter()
    status = 500  # what the client gets if the handler raises
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        user_id = getattr(request.state, "user_id", None)  # set by get_current_user
        access_log.info(
            json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                    "method": request.method,
                    "path": route.path if route else request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "user_id": str(user_id) if user_id else None,
                    "ip": client_ip(request),
                }
            )
        )


# Real models in production; tests override both, so they never load a model or touch the network.
@lru_cache
def get_embedder() -> Callable[[list[str]], Sequence[np.ndarray]]:
    return embed_documents


@lru_cache
def get_chunk_tokenizer() -> Callable[[], Tokenizer]:
    return get_tokenizer


SSE_RESPONSE = {
    200: {
        "description": "Server-Sent Events: `data` lines with answer tokens, then `sources` "
        "(citations), then `done` (the saved message id); `error` if the model failed.",
        "content": {"text/event-stream": {"example": 'data: "Use a default value"\n\n'}},
    }
}


# Order matters: the token is checked first, so unauthenticated requests never touch the limiter.
@app.post(
    "/chat",
    tags=["chat"],
    summary="Ask a question (streaming)",
    description="Answers from the knowledge base and the caller's own documents, with citations, "
    "or says it does not know. The session must be the caller's.",
    dependencies=[Depends(get_current_user), Depends(limit_per_ip)],
    responses={**SSE_RESPONSE, 401: R401, 404: R404, 422: R422, 429: R429},
)
async def chat(
    request: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    store: Annotated[Store, Depends(get_store)],
    global_limiter: Annotated[SlidingWindowLimiter, Depends(get_global_limiter)],
) -> StreamingResponse:
    body = await start_answer(
        provider=provider,
        settings=settings,
        retriever=retriever,
        store=store,
        global_limiter=global_limiter,
        user_id=user.id,
        session_id=request.session_id,
        message=request.message,
    )
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/flashcards",
    tags=["flashcards"],
    summary="Make flashcards from an answer",
    description="3-5 flashcards from one saved assistant answer and the chunks it cited. "
    "Costs one LLM call. The session must be the caller's.",
    dependencies=[Depends(get_current_user), Depends(limit_per_ip)],
    response_model=FlashcardSet,
    responses={
        401: R401,
        404: R404,
        422: {"description": "Validation error, or the answer has no sources to learn from"},
        429: R429,
        502: {"description": "The model failed or answered in a wrong format"},
    },
)
async def flashcards(
    request: FlashcardRequest,
    user: Annotated[User, Depends(get_current_user)],
    provider: Annotated[LLMProvider, Depends(get_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
    global_limiter: Annotated[SlidingWindowLimiter, Depends(get_global_limiter)],
) -> FlashcardSet:
    return await make_flashcards(
        provider=provider,
        settings=settings,
        store=store,
        global_limiter=global_limiter,
        user_id=user.id,
        session_id=request.session_id,
        message_id=request.message_id,
    )


@app.get(
    "/chunks/{chunk_id}",
    tags=["chunks"],
    summary="Text behind a citation",
    description="A shared knowledge-base chunk or one of the caller's own. Someone else's "
    "uploaded chunk answers 404, exactly like a missing one: ids must not be enumerable.",
    response_model=ChunkOut,
    dependencies=[Depends(get_current_user)],
    responses={401: R401, 404: R404, 422: R422},
)
async def chunk_text(
    chunk_id: Annotated[int, PathParam(ge=1, le=2**63 - 1)],  # chunks.id is a Postgres bigint
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
) -> dict:
    found = await asyncio.to_thread(store.get_chunks, [chunk_id], user.id)
    if not found:
        raise HTTPException(status_code=404, detail="Chunk not found")
    c = found[0]
    return {"id": c.id, "file": c.file_path, "heading": c.heading, "content": c.content}


def document_json(d: StoredDocument) -> dict:
    return {"id": d.id, "filename": d.filename, "chunks": d.chunks, "created_at": d.created_at}


@app.post(
    "/documents",
    status_code=201,
    tags=["documents"],
    summary="Upload a document",
    description="A .md / .txt / .pdf (text layer) into the caller's own space: it is chunked, "
    "embedded and searchable by this account only.",
    dependencies=[Depends(get_current_user), Depends(limit_per_ip)],
    response_model=DocumentOut,
    responses={
        401: R401,
        409: {"description": "The document limit per account is reached"},
        413: {"description": "The file is too large"},
        422: {"description": "Unsupported type, no text, or a validation error"},
        429: R429,
    },
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
    embedder: Annotated[Callable[[list[str]], Sequence[np.ndarray]], Depends(get_embedder)],
    tokenizer: Annotated[Callable[[], Tokenizer], Depends(get_chunk_tokenizer)],
    search: Annotated[SearchService, Depends(get_search_service)],
) -> dict:
    owner_id = user.id
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

        def save() -> StoredDocument:
            # The DB write and the index update are ONE code path: the index is touched only
            # after the commit succeeded (an exception above leaves it alone), so a request never
            # leaves a searchable chunk that is not in the DB.
            stored = store.add_document(
                owner_id, name, chunks, vectors, settings.max_documents_per_owner
            )
            try:
                search.add_chunks(
                    IndexRow(cid, owner_id, c.heading, c.content)
                    for cid, c in zip(stored.chunk_ids, chunks, strict=True)
                )
            except Exception:  # the document IS stored: keep the upload, fix the index on restart
                logger.exception("search index update failed after upload; restart rebuilds it")
            return stored

        doc = await asyncio.to_thread(save)
    except DocumentError as e:
        raise HTTPException(status_code=e.status, detail=e.detail) from None
    except TooManyDocuments:
        raise HTTPException(
            status_code=409,
            detail=f"You can keep at most {settings.max_documents_per_owner} documents. "
            "Delete one first.",
        ) from None
    return document_json(doc)


@app.get(
    "/documents",
    tags=["documents"],
    summary="List my documents",
    description="The caller's uploaded documents with their chunk counts, oldest first.",
    response_model=list[DocumentOut],
    dependencies=[Depends(get_current_user)],
    responses={401: R401},
)
async def list_documents(
    user: Annotated[User, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]
) -> list[dict]:
    return [document_json(d) for d in await asyncio.to_thread(store.list_documents, user.id)]


@app.delete(
    "/documents/{document_id}",
    status_code=204,
    tags=["documents"],
    summary="Delete a document",
    description="Deletes the document and its chunks. Someone else's document is a plain 404.",
    dependencies=[Depends(get_current_user)],
    responses={401: R401, 404: R404, 422: R422},
)
async def delete_document(
    document_id: Annotated[int, PathParam(ge=1, le=2**63 - 1)],
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
    search: Annotated[SearchService, Depends(get_search_service)],
) -> Response:
    def remove() -> bool:
        deleted = store.delete_document(user.id, document_id)  # chunk ids, None if not theirs
        if deleted is None:
            return False
        search.remove_chunks(deleted)  # only after the DB delete succeeded
        return True

    if not await asyncio.to_thread(remove):
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(status_code=204)


@app.get(
    "/health",
    tags=["system"],
    summary="Liveness",
    description="Answers 200 while the process is up. No login and deliberately no database "
    "check: a hosting platform restarts the app when this fails, and a database outage must "
    "not cause restarts.",
    response_model=HealthOut,
)
async def health() -> HealthOut:
    return HealthOut()


@app.get(
    "/",
    tags=["system"],
    summary="API docs",
    description="Redirects to the interactive API docs.",
    include_in_schema=False,
)
async def index() -> RedirectResponse:
    return RedirectResponse("/docs")
