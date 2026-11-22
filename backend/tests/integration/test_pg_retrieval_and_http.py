"""pgvector search with ownership, and one HTTP flow through the real store."""

import psycopg
import pytest
from fastapi.testclient import TestClient

from mnemonic import retrieval
from mnemonic.config import Settings, get_settings
from mnemonic.ingest import db
from mnemonic.ingest.chunker import Chunk as NewChunk
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_chunk_tokenizer, get_embedder, get_provider, get_retriever
from mnemonic.store import PgStore, get_store

from ..fakes import FakeRetriever
from ..test_documents import MD, WordTokenizer, fake_embedder
from .test_pg_store import vec

pytestmark = pytest.mark.integration


def test_retriever_sees_shared_and_own_chunks_only(pg_store, pg_url, monkeypatch):
    alice = pg_store.create_user("alice@example.com", "h")
    bob = pg_store.create_user("bob@example.com", "h")
    with db.connect(pg_url) as conn:
        db.upsert_chunks(conn, [NewChunk("tutorial/cors.md", "CORS", 0, "shared")], [vec(0, 1)])
    pg_store.add_document(alice.id, "a.md", [NewChunk("a.md", "A", 0, "alice")], [vec(0)], 5)
    # Bob's chunk is the closest of all to the question: it must still never reach Alice.
    pg_store.add_document(bob.id, "b.md", [NewChunk("b.md", "B", 0, "bob")], [vec(0)], 5)
    monkeypatch.setattr(retrieval, "embed_query", lambda q: vec(0))  # no model download

    with db.connect(pg_url) as conn:
        for_alice = retrieval.retrieve(conn, "question", k=10, owner_id=alice.id)
        anonymous = retrieval.retrieve(conn, "question", k=10, owner_id=None)

    assert [h.content for h in for_alice] == ["alice", "shared"]  # best first
    assert for_alice[0].similarity == pytest.approx(1.0)
    assert for_alice[1].similarity == pytest.approx(2**-0.5)  # cos 45 degrees
    assert [h.content for h in anonymous] == ["shared"]


@pytest.fixture
def pg_client(pg_url):
    """The real app on the real PgStore; only the LLM, embedder and tokenizer are fakes."""
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, database_url=pg_url)
    app.dependency_overrides[get_store] = lambda: PgStore(pg_url)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([])
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_chunk_tokenizer] = lambda: WordTokenizer
    with TestClient(app) as client:
        yield client


def sign_up(client, email: str) -> dict:
    password = "correct horse battery"
    created = client.post("/auth/register", json={"email": email, "password": password})
    assert created.status_code == 201, created.text
    token = client.post("/auth/login", data={"username": email, "password": password})
    assert token.status_code == 200, token.text
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def test_http_register_login_session_upload_and_a_stranger_gets_404(pg_client, pg_url):
    alice = sign_up(pg_client, "alice@example.com")

    session = pg_client.post("/sessions", json={"title": "Biology"}, headers=alice)
    assert session.status_code == 201
    sid = session.json()["id"]
    doc = pg_client.post(
        "/documents", files={"file": ("notes.md", MD, "application/octet-stream")}, headers=alice
    )
    assert doc.status_code == 201, doc.text
    doc_id = doc.json()["id"]

    # The rows really are in Postgres, and the password is stored as an argon2 hash.
    with psycopg.connect(pg_url) as conn:
        (password_hash,) = conn.execute(
            "SELECT password_hash FROM users WHERE email = 'alice@example.com'"
        ).fetchone()
        (chunks,) = conn.execute(
            "SELECT count(*) FROM chunks WHERE document_id = %s", (doc_id,)
        ).fetchone()
    assert password_hash.startswith("$argon2id$")
    assert chunks >= 1

    bob = sign_up(pg_client, "bob@example.com")
    assert pg_client.get(f"/sessions/{sid}", headers=bob).status_code == 404
    assert pg_client.get(f"/sessions/{sid}/messages", headers=bob).status_code == 404
    assert pg_client.delete(f"/documents/{doc_id}", headers=bob).status_code == 404
    assert pg_client.get("/documents", headers=bob).json() == []
    assert pg_client.get("/sessions", headers=bob).json()["total"] == 0
    # ...while Alice still has both.
    assert pg_client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "Biology"
    assert [d["id"] for d in pg_client.get("/documents", headers=alice).json()] == [doc_id]
    assert pg_client.get("/sessions").status_code == 401  # no token at all
