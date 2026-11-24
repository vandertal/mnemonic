"""Search service + hybrid retrieval: RRF, the gates, vector-mode parity, index lifecycle."""

import threading
import uuid

import pytest

from mnemonic import retrieval
from mnemonic.retrieval import (
    GATES,
    Hit,
    HybridRetriever,
    gate_vector,
    gate_vector_or_lexical,
    gate_vector_or_specific_lexical,
    is_answerable,
    rrf,
)
from mnemonic.search_service import SearchService
from mnemonic.store import IndexRow

from .fakes import MemoryStore
from .test_search_api import MD_BOB, MD_TOKEN, VEC, FakeSource

ALICE, BOB = uuid.uuid4(), uuid.uuid4()


def row(id: int, content: str, owner=None, heading: str = "H") -> IndexRow:
    return IndexRow(id, owner, heading, content)


# --- RRF ----------------------------------------------------------------------------------


def test_rrf_on_hand_made_rankings():
    fused = dict(rrf([[1, 2, 3], [3, 1, 4]], k=60))
    assert fused[1] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[3] == pytest.approx(1 / 63 + 1 / 61)
    assert fused[2] == pytest.approx(1 / 62)
    assert fused[4] == pytest.approx(1 / 63)
    # 1 (ranks 1,2) beats 3 (ranks 3,1): the sum of reciprocals decides, not the best rank.
    assert [i for i, _ in rrf([[1, 2, 3], [3, 1, 4]])] == [1, 3, 2, 4]


def test_rrf_uses_only_ranks_and_keeps_first_seen_order_on_ties():
    assert [i for i, _ in rrf([[7, 8], [9, 10]])] == [7, 9, 8, 10]  # ties: first list first
    assert rrf([]) == [] and rrf([[], []]) == []
    assert [i for i, _ in rrf([[5]])] == [5]


# --- the gates ----------------------------------------------------------------------------


def hit(sim: float, lexical_all: bool = False, max_df: float = 1.0) -> Hit:
    return Hit(1, sim, "f.md", "h", "c", lexical_all, max_df)


def test_gate_a_is_the_vector_threshold():
    assert gate_vector([hit(0.80)], 0.77)
    assert not gate_vector([hit(0.70, lexical_all=True)], 0.77)  # lexical is ignored
    assert not gate_vector([], 0.77)
    assert gate_vector([hit(0.5), hit(0.9)], 0.77)  # the best hit counts, wherever it is


def test_gate_b_adds_the_lexical_rule():
    assert gate_vector_or_lexical([hit(0.5, lexical_all=True)], 0.77)
    assert not gate_vector_or_lexical([hit(0.5)], 0.77)
    assert gate_vector_or_lexical([hit(0.9)], 0.77)
    assert gate_vector_or_lexical([hit(0.5, lexical_all=True, max_df=0.9)], 0.77)  # any df


def test_gate_c_ignores_lexical_matches_on_very_common_terms():
    assert gate_vector_or_specific_lexical([hit(0.5, True, max_df=0.02)], 0.77)
    assert gate_vector_or_specific_lexical([hit(0.5, True, max_df=0.1)], 0.77)  # boundary
    assert not gate_vector_or_specific_lexical([hit(0.5, True, max_df=0.17)], 0.77)
    assert gate_vector_or_specific_lexical([hit(0.9, True, max_df=0.9)], 0.77)  # vector still wins
    assert set(GATES) == {"a", "b", "c"}


def test_vector_mode_always_uses_the_original_gate():
    lexical_only = [hit(0.5, True, 0.01)]
    assert is_answerable(lexical_only, 0.77, "hybrid")
    assert not is_answerable(lexical_only, 0.77, "vector")


# --- vector mode == the old behaviour -----------------------------------------------------


def test_vector_mode_is_exactly_the_old_pgvector_call(monkeypatch):
    calls = []
    rows = [(1, 0.9, "a.md", "A", "alpha"), (2, 0.8, "b.md", "B", "beta")]

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(retrieval.db, "connect", lambda url: Conn())
    monkeypatch.setattr(
        retrieval.db, "search", lambda conn, vec, k, owner: calls.append((vec, k, owner)) or rows
    )
    monkeypatch.setattr(retrieval, "embed_query", lambda q: VEC)

    class Boom(SearchService):  # any use of the index in vector mode is a bug
        @property
        def ready(self):
            raise AssertionError("vector mode must not look at the index")

    hits = retrieval.PgRetriever("postgresql://x", 5, "vector", Boom())("question", ALICE)
    assert calls == [(VEC, 5, ALICE)]  # same query, k = top_k (no candidates), same owner
    assert hits == [retrieval.Hit(*r) for r in rows]
    assert all(not h.lexical_all for h in hits)


def test_hybrid_falls_back_to_vector_until_the_index_is_ready():
    store = MemoryStore()
    source = FakeSource(store)
    store.chunks[1] = retrieval_chunk(1, "cors")
    store.chunk_owner[1] = None
    r = HybridRetriever(source, 5, "hybrid", SearchService(), embed=lambda q: VEC)
    assert [h.id for h in r("cors", None)] == [1]  # served by the vector path


def retrieval_chunk(id: int, content: str):
    from mnemonic.store import Chunk

    return Chunk(id, f"doc{id}.md", f"Heading {id}", content)


# --- hybrid fusion end to end -------------------------------------------------------------


def test_hybrid_returns_top_k_in_rrf_order_with_lexical_only_hits():
    store = MemoryStore()
    for i in range(1, 9):
        store.chunks[i] = retrieval_chunk(i, f"filler text number {i}")
        store.chunk_owner[i] = None
    store.chunks[9] = retrieval_chunk(9, "the zebrafish keyword lives here")
    store.chunk_owner[9] = None
    service = SearchService()
    service.build(store.index_rows())
    source = FakeSource(store, similarity=0.4)  # vector order = id order, ids 1..8 first
    r = HybridRetriever(source, 5, "hybrid", service, candidates=8, embed=lambda q: VEC)
    hits = r("zebrafish", None)
    assert len(hits) == 5
    # Chunk 9 is NOT in the vector candidates (top 8) but is rank 1 lexically: it is fetched.
    assert hits[0].id in (1, 9) and 9 in [h.id for h in hits]
    fetched = next(h for h in hits if h.id == 9)
    assert fetched.similarity == 0.4 and fetched.file_path == "doc9.md"
    assert fetched.lexical_all  # the chunk holds every query term
    assert not any(h.lexical_all for h in hits if h.id != 9)


def test_bm25_mode_returns_only_lexical_hits():
    store = MemoryStore()
    for i, text in enumerate(["alpha beta", "gamma delta", "alpha alpha"], start=1):
        store.chunks[i] = retrieval_chunk(i, text)
        store.chunk_owner[i] = None
    service = SearchService()
    service.build(store.index_rows())
    r = HybridRetriever(FakeSource(store), 5, "bm25", service, embed=lambda q: VEC)
    assert {h.id for h in r("alpha", None)} == {1, 3}


# --- index lifecycle ----------------------------------------------------------------------


def snapshot(service: SearchService, query: str, allowed) -> list:
    return [(h.doc_id, round(h.score, 9)) for h in service.search(query, allowed_ids=allowed)]


def test_incremental_add_and_remove_equal_a_fresh_rebuild():
    base = [row(1, "cors middleware", None), row(2, "depends injection", None)]
    inc = SearchService()
    inc.build(base)
    inc.add_chunks([row(3, "websocket cors", ALICE), row(4, "pydantic model", ALICE)])
    inc.remove_chunks([2, 4])
    inc.add_chunks([row(5, "background tasks cors", BOB)])

    fresh = SearchService()
    fresh.build([row(1, "cors middleware", None), row(3, "websocket cors", ALICE),
                 row(5, "background tasks cors", BOB)])  # fmt: skip
    everything = {"1", "2", "3", "4", "5"}
    for q in ("cors", "websocket", "tasks cors", "depends", "pydantic"):
        assert snapshot(inc, q, everything) == snapshot(fresh, q, everything), q
    assert len(inc) == len(fresh) == 3
    assert inc.allowed_ids() == fresh.allowed_ids() == {"1"}  # only shared ids are cached


def test_updates_during_a_build_are_not_lost():
    service = SearchService()
    gate = threading.Event()

    def slow_rows():
        yield row(1, "first chunk", None)
        gate.wait(5)  # the build is paused here: it has read part of the DB only
        yield row(2, "second chunk", None)

    builder = threading.Thread(target=lambda: service.build(slow_rows()))
    builder.start()
    for _ in range(100):  # wait until the build has begun (journal armed)
        if service._journal is not None:
            break
        threading.Event().wait(0.01)
    service.add_chunks([row(3, "uploaded meanwhile", ALICE)])
    service.remove_chunks([1])
    gate.set()
    builder.join(5)
    assert service.ready
    ids = {"1", "2", "3"}
    assert snapshot(service, "meanwhile", ids)[0][0] == "3"
    assert snapshot(service, "first", ids) == []  # the removal was replayed too
    assert snapshot(service, "second", ids)[0][0] == "2"


def test_search_requires_an_explicit_allowed_set():
    with pytest.raises(TypeError):
        SearchService().search("x")  # type: ignore[call-arg]


def test_explain_refuses_chunks_outside_the_allowed_set():
    service = SearchService()
    service.build([row(1, "cors", None), row(2, "secret cors", ALICE)])
    assert service.explain("cors", 1, allowed_ids={"1"}).terms[0].tf == 1
    with pytest.raises(KeyError):
        service.explain("cors", 2, allowed_ids={"1"})  # exists, but not visible
    with pytest.raises(KeyError):
        service.explain("cors", 99, allowed_ids={"1", "99"})  # visible id, not indexed


# --- ownership inside the retriever -------------------------------------------------------


def seeded_store() -> MemoryStore:
    store = MemoryStore()
    store.chunks[7] = retrieval_chunk(7, "shared cors guide")
    store.chunk_owner[7] = None
    store.chunks[100] = retrieval_chunk(100, f"alice private {MD_TOKEN}")
    store.chunk_owner[100] = ALICE
    store.chunks[101] = retrieval_chunk(101, f"bob private {MD_BOB}")
    store.chunk_owner[101] = BOB
    return store


@pytest.mark.parametrize("mode", ["vector", "bm25", "hybrid"])
def test_a_user_never_gets_a_foreign_chunk_from_the_retriever(mode):
    store = seeded_store()
    service = SearchService()
    service.build(store.index_rows())
    source = FakeSource(store, leaky_fetch=True)  # a fetch that ignores ownership must not matter
    r = HybridRetriever(source, 5, mode, service, embed=lambda q: VEC)
    for owner, forbidden in ((BOB, {100}), (ALICE, {101}), (None, {100, 101})):
        for question in (MD_TOKEN, MD_BOB, "private", "cors"):
            ids = {h.id for h in r(question, owner)}
            assert not ids & forbidden, (mode, owner, question, ids)
