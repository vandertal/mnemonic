"""The search index against a real Postgres: startup build, ingest -> searchable, delete -> gone."""

import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.ingest import db
from mnemonic.ingest.chunker import Chunk as NewChunk
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_chunk_tokenizer, get_embedder, get_provider, get_retriever
from mnemonic.search_service import SearchService, get_search_service
from mnemonic.store import PgStore, get_store

from ..fakes import FakeRetriever
from ..test_documents import WordTokenizer, fake_embedder
from .test_pg_retrieval_and_http import sign_up
from .test_pg_store import vec

pytestmark = pytest.mark.integration


@contextmanager
def running_app(pg_url):
    """The real app on the real PgStore (LLM, embedder and tokenizer are fakes). The lifespan
    builds the index from whatever is in the database at this moment."""
    svc = SearchService()
    app.dependency_overrides[get_search_service] = lambda: svc
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, database_url=pg_url)
    app.dependency_overrides[get_store] = lambda: PgStore(pg_url)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([])
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_chunk_tokenizer] = lambda: WordTokenizer
    with TestClient(app) as client:
        for _ in range(500):  # the build runs in a worker thread
            if svc.ready:
                break
            time.sleep(0.01)
        assert svc.ready, "the startup build did not finish"
        yield client, svc


def md(token: str) -> bytes:
    return f"# Notes\n\nThe {token} appears here.\n".encode()


def test_store_reports_chunk_ids_for_the_index(pg_store):
    alice = pg_store.create_user("alice@example.com", "h")
    chunks = [NewChunk("a.md", "A", i, f"alice part {i}") for i in range(3)]
    doc = pg_store.add_document(alice.id, "a.md", chunks, [vec(i) for i in range(3)], 5)
    assert len(doc.chunk_ids) == 3
    assert pg_store.owned_chunk_ids(alice.id) == sorted(doc.chunk_ids)
    rows = {r.id: r for r in pg_store.index_rows()}
    assert [rows[i].content for i in doc.chunk_ids] == [c.content for c in chunks]  # in order
    assert all(rows[i].owner_id == alice.id for i in doc.chunk_ids)
    assert pg_store.delete_document(alice.id, doc.id) == list(doc.chunk_ids)
    assert pg_store.owned_chunk_ids(alice.id) == [] and pg_store.index_rows() == []


def test_startup_builds_the_index_from_the_database(pg_store, pg_url):
    alice = pg_store.create_user("alice@example.com", "h")
    with db.connect(pg_url) as conn:  # a shared knowledge-base chunk, as the ingest CLI writes it
        db.upsert_chunks(
            conn, [NewChunk("tutorial/cors.md", "CORS", 0, "Use CORSMiddleware.")], [vec(0)]
        )
    pg_store.add_document(
        alice.id, "a.md", [NewChunk("a.md", "A", 0, "quokkaprivate")], [vec(1)], 5
    )

    with running_app(pg_url) as (client, svc):
        assert len(svc) == 2
        alice_h = sign_up(client, "alice2@example.com")  # a different account
        shared = client.get("/search", params={"q": "corsmiddleware"}, headers=alice_h)
        assert [h["document"] for h in shared.json()] == ["tutorial/cors.md"]
        # the first account's private chunk is in the index but invisible to the second one
        assert client.get("/search", params={"q": "quokkaprivate"}, headers=alice_h).json() == []


def test_upload_is_searchable_and_delete_removes_it(pg_url):
    with running_app(pg_url) as (client, svc):
        alice, bob = sign_up(client, "alice@example.com"), sign_up(client, "bob@example.com")
        up = client.post(
            "/documents",
            files={"file": ("n.md", md("zebrafishquokka"), "text/markdown")},
            headers=alice,
        )
        assert up.status_code == 201, up.text
        doc_id = up.json()["id"]

        hits = client.get("/search", params={"q": "zebrafishquokka"}, headers=alice).json()
        assert len(hits) == 1 and hits[0]["document"] == "n.md"
        cid = hits[0]["chunk_id"]
        assert client.get("/search", params={"q": "zebrafishquokka"}, headers=bob).json() == []
        explain = {"q": "zebrafishquokka", "chunk_id": cid}
        assert client.get("/search/explain", params=explain, headers=alice).status_code == 200
        assert client.get("/search/explain", params=explain, headers=bob).status_code == 404

        assert client.delete(f"/documents/{doc_id}", headers=alice).status_code == 204
        assert client.get("/search", params={"q": "zebrafishquokka"}, headers=alice).json() == []
        assert str(cid) not in svc._engine.index

    # A restart (a fresh build from the database) agrees with the incremental state.
    fresh = SearchService()
    fresh.build(PgStore(pg_url).index_rows())
    assert len(fresh) == 0
