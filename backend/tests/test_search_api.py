"""GET /search and /search/explain: validation, ranking, ownership (Alice/Bob), snippets."""

import time
from contextlib import contextmanager

import numpy as np
import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.main import app, get_chunk_tokenizer, get_embedder, get_retriever
from mnemonic.retrieval import Hit, HybridRetriever
from mnemonic.search_service import SearchService, get_search_service
from mnemonic.security import get_global_limiter, get_ip_limiter
from mnemonic.store import Chunk, get_store

from .fakes import FakeRetriever, MemoryStore, login
from .test_documents import WordTokenizer, fake_embedder

ALICE, BOB = "alice@example.com", "bob@example.com"
VEC = np.zeros(3, dtype=np.float32)
MD_TOKEN = "zebrafishquokka"
MD_BOB = "narwhalmarmot"
SHARED_ID = 7


def md(token: str) -> bytes:
    return f"# Notes\n\nThe {token} appears here.\n".encode()


class FakeSource:
    """ChunkSource over a MemoryStore. `leaky_fetch` simulates a DB layer that forgets the
    ownership filter in fetch(): the ids it is asked for must already be filtered upstream."""

    def __init__(self, store: MemoryStore, similarity: float = 0.5, leaky_fetch: bool = False):
        self.store, self.similarity, self.leaky_fetch = store, similarity, leaky_fetch

    @contextmanager
    def session(self):
        yield self

    def _hit(self, cid: int) -> Hit:
        c = self.store.chunks[cid]
        return Hit(cid, self.similarity, c.file_path, c.heading, c.content)

    def _visible(self, owner_id) -> list[int]:
        owners = (None, owner_id)
        return [c for c in sorted(self.store.chunks) if self.store.chunk_owner.get(c) in owners]

    def vector_search(self, qvec, owner_id, n):
        return [self._hit(c) for c in self._visible(owner_id)][:n]

    def fetch(self, qvec, ids, owner_id):
        allowed = set(ids) if self.leaky_fetch else set(ids) & set(self._visible(owner_id))
        return [self._hit(c) for c in sorted(allowed) if c in self.store.chunks]

    def owned_ids(self, owner_id):
        return self.store.owned_chunk_ids(owner_id)


@pytest.fixture
def store():
    s = MemoryStore()
    s.chunks[SHARED_ID] = Chunk(
        SHARED_ID, "tutorial/cors.md", "CORS", "Use CORSMiddleware to configure CORS origins."
    )
    s.chunks[8] = Chunk(8, "tutorial/dependencies/index.md", "Depends", "Depends declares one.")
    return s


@pytest.fixture
def service(store):
    svc = SearchService()
    svc.build(store.index_rows())
    app.dependency_overrides[get_search_service] = lambda: svc
    return svc


@pytest.fixture
def client(store, service):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([])
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_chunk_tokenizer] = lambda: WordTokenizer
    with TestClient(app) as c:
        yield c


def hdr(store, who=ALICE) -> dict:
    return login(store, who)


def upload(client, store, who, token) -> dict:
    r = client.post(
        "/documents",
        files={"file": ("notes.md", md(token), "text/markdown")},
        headers=hdr(store, who),
    )
    assert r.status_code == 201, r.text
    return r.json()


def user_of(store, who):
    return store.get_user_by_email(who)[0].id


def chunk_id_of(store, who) -> int:
    return store.owned_chunk_ids(user_of(store, who))[0]


def get(client, store, path, who=ALICE, **params):
    return client.get(path, params=params, headers=hdr(store, who))


# --- auth and validation ------------------------------------------------------------------


def test_search_and_explain_need_a_token(client):
    assert client.get("/search", params={"q": "cors"}).status_code == 401
    assert client.get("/search/explain", params={"q": "cors", "chunk_id": 7}).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.get("/search", params={"q": "cors"}, headers=bad).status_code == 401


@pytest.mark.parametrize(
    "params",
    [
        {},  # q missing
        {"q": ""},
        {"q": "   "},  # blank
        {"q": "x" * 201},
        {"q": "cors", "limit": 0},
        {"q": "cors", "limit": 51},
        {"q": "cors", "limit": "ten"},
        {"q": "cors", "mode": "some"},
        {"q": "cors", "ranker": "pagerank"},
    ],
)
def test_search_rejects_bad_parameters(client, store, params):
    assert get(client, store, "/search", **params).status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"q": "cors"},
        {"chunk_id": 7},
        {"q": " ", "chunk_id": 7},
        {"q": "cors", "chunk_id": 0},
        {"q": "cors", "chunk_id": "x"},
        {"q": "cors", "chunk_id": 7, "ranker": "x"},
    ],
)
def test_explain_rejects_bad_parameters(client, store, params):
    assert get(client, store, "/search/explain", **params).status_code == 422


def test_limit_bounds_are_inclusive_and_respected(client):
    many = MemoryStore()
    for i in range(1, 61):
        many.chunks[i] = Chunk(i, f"d{i}.md", "H", f"common word {i}")
    svc = SearchService()
    svc.build(many.index_rows())
    app.dependency_overrides[get_store] = lambda: many
    app.dependency_overrides[get_search_service] = lambda: svc
    assert len(get(client, many, "/search", q="common", limit=50).json()) == 50
    assert len(get(client, many, "/search", q="common", limit=1).json()) == 1
    assert len(get(client, many, "/search", q="common").json()) == 10  # the default


def test_search_uses_the_per_ip_limit_not_the_llm_budget(client, store):
    ip, budget = SlidingWindowLimiter(2), SlidingWindowLimiter(1000)
    app.dependency_overrides[get_ip_limiter] = lambda: ip
    app.dependency_overrides[get_global_limiter] = lambda: budget
    codes = [get(client, store, "/search", q="cors").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert budget._hits == {} or budget.acquire("global") is None  # nothing was spent


def test_search_answers_503_until_the_index_is_ready(client, store):
    app.dependency_overrides[get_search_service] = lambda: SearchService()  # never built
    r = get(client, store, "/search", q="cors")
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert get(client, store, "/search/explain", q="cors", chunk_id=7).status_code == 503


# --- results ------------------------------------------------------------------------------


def test_search_returns_ranked_hits_with_snippet_offsets(client, store):
    r = get(client, store, "/search", q="cors origins")
    assert r.status_code == 200
    (hit,) = r.json()
    assert hit["chunk_id"] == SHARED_ID and hit["document"] == "tutorial/cors.md"
    assert hit["heading"] == "CORS" and hit["score"] > 0
    assert set(hit["matched_terms"]) == {"cors", "origins"}
    text = hit["snippet"]["text"]
    for start, end in hit["snippet"]["highlights"]:
        assert text[start:end].lower() in {"cors", "origins", "corsmiddleware"}  # whole identifier


def test_mode_any_widens_and_all_narrows(client, store):
    assert get(client, store, "/search", q="cors depends").json() == []  # no chunk has both
    both = get(client, store, "/search", q="cors depends", mode="any").json()
    assert {h["chunk_id"] for h in both} == {SHARED_ID, 8}


def test_stop_word_only_query_is_an_empty_list_not_an_error(client, store):
    r = get(client, store, "/search", q="the and of")
    assert r.status_code == 200 and r.json() == []


def test_explain_contributions_sum_to_the_score(client, store):
    for ranker in ("bm25", "tfidf"):
        q = {"q": "cors origins configure", "ranker": ranker}
        (hit,) = get(client, store, "/search", **q).json()
        e = get(client, store, "/search/explain", chunk_id=SHARED_ID, **q).json()
        assert e["document"] == "tutorial/cors.md" and e["ranker"] == ranker
        assert sum(t["contribution"] for t in e["terms"]) == pytest.approx(e["score"])
        assert e["score"] == pytest.approx(hit["score"])
        assert all(t["tf"] >= 1 and t["df"] >= 1 and t["idf"] != 0 for t in e["terms"])
        assert e["n_docs"] == 2 and e["doc_length"] > 0


def test_explain_unknown_chunk_is_404(client, store):
    assert get(client, store, "/search/explain", q="cors", chunk_id=424242).status_code == 404


# --- ownership matrix: Alice / Bob --------------------------------------------------------


def test_bob_never_sees_alices_chunk(client, store, service):
    upload(client, store, ALICE, MD_TOKEN)
    cid = chunk_id_of(store, ALICE)

    mine = get(client, store, "/search", q=MD_TOKEN).json()
    assert [h["chunk_id"] for h in mine] == [cid]
    assert get(client, store, "/search/explain", q=MD_TOKEN, chunk_id=cid).status_code == 200

    login(store, BOB)
    for mode in ("all", "any"):
        assert get(client, store, "/search", BOB, q=MD_TOKEN, mode=mode).json() == []
    # explain: the chunk exists but is Alice's -> exactly the same 404 as for a missing one
    foreign = get(client, store, "/search/explain", BOB, q=MD_TOKEN, chunk_id=cid)
    missing = get(client, store, "/search/explain", BOB, q=MD_TOKEN, chunk_id=cid + 999)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    # the index does hold the chunk: it is the allowed set that hides it
    assert str(cid) in service._engine.index


def test_bob_does_not_get_alices_chunk_as_a_rag_source(client, store, service):
    upload(client, store, ALICE, MD_TOKEN)
    upload(client, store, BOB, MD_BOB)
    alice_id, bob_id = chunk_id_of(store, ALICE), chunk_id_of(store, BOB)
    bob, alice = user_of(store, BOB), user_of(store, ALICE)
    source = FakeSource(store, leaky_fetch=True)
    retriever = HybridRetriever(source, 5, "hybrid", service, embed=lambda q: VEC)
    assert alice_id not in {h.id for h in retriever(MD_TOKEN, bob)}
    assert bob_id not in {h.id for h in retriever(MD_BOB, alice)}
    assert alice_id in {h.id for h in retriever(MD_TOKEN, alice)}  # and Alice does get her own


def test_deleting_a_document_removes_it_from_search_at_once(client, store, service):
    doc = upload(client, store, ALICE, MD_TOKEN)
    cid = chunk_id_of(store, ALICE)
    assert len(get(client, store, "/search", q=MD_TOKEN).json()) == 1
    login(store, BOB)
    assert client.delete(f"/documents/{doc['id']}", headers=hdr(store, BOB)).status_code == 404
    assert len(get(client, store, "/search", q=MD_TOKEN).json()) == 1  # Bob's try changed nothing
    assert client.delete(f"/documents/{doc['id']}", headers=hdr(store, ALICE)).status_code == 204
    assert get(client, store, "/search", q=MD_TOKEN).json() == []
    assert str(cid) not in service._engine.index  # gone from memory, not just hidden
    assert get(client, store, "/search/explain", q=MD_TOKEN, chunk_id=cid).status_code == 404


def test_deleting_an_account_removes_its_chunks_from_the_index(client, store, service):
    upload(client, store, ALICE, MD_TOKEN)
    cid = chunk_id_of(store, ALICE)
    assert client.delete("/auth/me", headers=hdr(store, ALICE)).status_code == 204
    assert str(cid) not in service._engine.index


def test_a_refused_upload_does_not_touch_the_index(client, store, service):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, max_documents_per_owner=1
    )
    upload(client, store, ALICE, MD_TOKEN)
    size = len(service)
    r = client.post(  # over the limit: the store refuses, so the index must stay as it was
        "/documents",
        files={"file": ("b.md", md("secondtoken"), "text/markdown")},
        headers=hdr(store, ALICE),
    )
    assert r.status_code == 409 and len(service) == size
    assert get(client, store, "/search", q="secondtoken").json() == []


def test_upload_makes_the_chunk_searchable_without_a_restart(client, store):
    assert get(client, store, "/search", q=MD_TOKEN).json() == []
    upload(client, store, ALICE, MD_TOKEN)
    assert len(get(client, store, "/search", q=MD_TOKEN).json()) == 1


# --- snippets are plain text --------------------------------------------------------------


def test_script_tags_come_back_as_plain_text_with_offsets(client, store):
    evil = "<script>alert(1)</script> quokkaxss <img src=x onerror=alert(2)>"
    r = client.post(
        "/documents",
        files={"file": ("x.md", f"# T\n\n{evil}\n".encode(), "text/markdown")},
        headers=hdr(store, ALICE),
    )
    assert r.status_code == 201
    resp = get(client, store, "/search", q="quokkaxss")
    assert resp.headers["content-type"] == "application/json"
    (hit,) = resp.json()
    text, spans = hit["snippet"]["text"], hit["snippet"]["highlights"]
    assert "<script>" in text  # verbatim TEXT: the client must draw it as text, never as HTML
    assert [text[s:e] for s, e in spans] == ["quokkaxss"]
    assert "<mark" not in text and "&lt;" not in text  # nothing added, nothing escaped away


# --- startup build from the store ---------------------------------------------------------


def test_startup_builds_the_index_from_the_store_in_the_background(store):
    svc = SearchService()
    app.dependency_overrides[get_search_service] = lambda: svc
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    login(store, ALICE)
    with TestClient(app) as c:
        for _ in range(300):
            if svc.ready:
                break
            time.sleep(0.01)
        assert svc.ready and len(svc) == 2
        r = c.get("/search", params={"q": "depends"}, headers=hdr(store))
        assert [h["chunk_id"] for h in r.json()] == [8]


def test_startup_survives_a_broken_store():
    class Broken(MemoryStore):
        def index_rows(self):
            raise RuntimeError("db down")

    svc = SearchService()
    app.dependency_overrides[get_search_service] = lambda: svc
    app.dependency_overrides[get_store] = lambda: Broken()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
    assert not svc.ready  # chat falls back to vector search, /search answers 503
