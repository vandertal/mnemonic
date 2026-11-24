"""Keyword search over the caller's visible chunks: GET /search and GET /search/explain."""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from mnemonic import events
from mnemonic.auth import get_current_user
from mnemonic.openapi import R401, R404, R422, R429
from mnemonic.schemas import ExplainOut, SearchHitOut, SnippetOut, TermExplanationOut
from mnemonic.search_service import SearchService, get_search_service
from mnemonic.security import limit_per_ip
from mnemonic.store import Store, User, get_store

# Token first, then the per-IP limiter (search costs no LLM tokens, so the global LLM budget is
# not touched). Unauthenticated requests never reach the limiter.
router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(get_current_user), Depends(limit_per_ip)],
    responses={401: R401, 422: R422, 429: R429},
)

CurrentUser = Annotated[User, Depends(get_current_user)]
StoreDep = Annotated[Store, Depends(get_store)]
ServiceDep = Annotated[SearchService, Depends(get_search_service)]
# `pattern=\S` rejects a blank query ("   ") that min_length alone would let through.
Q = Annotated[
    str,
    Query(
        min_length=1,
        max_length=200,
        pattern=r"\S",
        description='Query: `foo bar`, `"exact phrase"`, `-excluded`.',
        examples=["response_model"],
    ),
]
Ranker = Annotated[Literal["bm25", "tfidf"], Query(description="Ranking function.")]


def not_ready() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="The search index is still being built. Try again in a few seconds.",
        headers={"Retry-After": "5"},
    )


def visible_ids(service: SearchService, store: Store, user: User) -> set[str]:
    """Visible chunk ids for this user: shared + their own (from the DB)."""
    return service.allowed_ids(store.owned_chunk_ids(user.id))


@router.get(
    "",
    response_model=list[SearchHitOut],
    summary="Search my chunks",
    description="Ranked chunks of the knowledge base and of the caller's own documents. Someone "
    "else's uploaded chunk is never returned. `mode=all`: every term must match; `any`: at "
    "least one. Stop words are ignored; there is no stemming.",
    responses={503: {"description": "The index is still being built after a restart"}},
)
async def search(
    q: Q,
    user: CurrentUser,
    store: StoreDep,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    mode: Annotated[Literal["all", "any"], Query()] = "all",
    ranker: Ranker = "bm25",
) -> list[SearchHitOut]:
    if not service.ready:
        raise not_ready()

    def work() -> list[SearchHitOut]:
        allowed = visible_ids(service, store, user)
        found = service.search(q, allowed_ids=allowed, mode=mode, limit=limit, ranker=ranker)
        # The DB confirms visibility once more and supplies file and heading: a chunk it does
        # not return to this user is dropped, whatever the index said.
        chunks = {c.id: c for c in store.get_chunks([int(h.doc_id) for h in found], user.id)}
        return [
            SearchHitOut(
                chunk_id=int(h.doc_id),
                document=chunks[int(h.doc_id)].file_path,
                heading=chunks[int(h.doc_id)].heading,
                score=h.score,
                snippet=SnippetOut(text=h.snippet.text, highlights=h.snippet.highlights),
                matched_terms=h.matched_terms,
            )
            for h in found
            if int(h.doc_id) in chunks
        ]

    hits = await asyncio.to_thread(work)
    await events.emit(store, events.SEARCH, user.id, results=bool(hits))
    return hits


@router.get(
    "/explain",
    response_model=ExplainOut,
    summary="Why this score? (teaching mode)",
    description="Per-term tf, df, idf and contribution for one chunk and one query; the "
    "contributions sum to the score. A chunk that does not exist or is not visible to the caller "
    "answers 404 (the two look the same).",
    responses={404: R404, 503: {"description": "The index is still being built"}},
)
async def explain(
    q: Q,
    chunk_id: Annotated[int, Query(ge=1, le=2**63 - 1)],
    user: CurrentUser,
    store: StoreDep,
    service: ServiceDep,
    ranker: Ranker = "bm25",
) -> ExplainOut:
    if not service.ready:
        raise not_ready()

    def work() -> ExplainOut | None:
        found = store.get_chunks([chunk_id], user.id)  # ownership, enforced by the DB query
        if not found:
            return None
        try:
            e = service.explain(
                q, chunk_id, allowed_ids=visible_ids(service, store, user), ranker=ranker
            )
        except KeyError:  # not in the index (or not visible)
            return None
        return ExplainOut(
            chunk_id=chunk_id,
            document=found[0].file_path,
            ranker=e.ranker,
            n_docs=e.n_docs,
            avgdl=e.avgdl,
            doc_length=e.terms[0].doc_length if e.terms else 0,
            terms=[
                TermExplanationOut(
                    term=t.term, tf=t.tf, df=t.df, idf=t.idf, contribution=t.contribution
                )
                for t in e.terms
            ],
            score=e.score,
        )

    result = await asyncio.to_thread(work)
    if result is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return result
