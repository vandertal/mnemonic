"""Ownership: every data endpoint is scoped to the user in the Bearer token (lab 21, M2)."""

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_chunk_tokenizer, get_embedder, get_provider, get_retriever
from mnemonic.store import DEFAULT_TITLE, Chunk, get_store

from .fakes import FakeRetriever, MemoryStore, RecordingProvider, login, make_hit, user_id
from .test_chat import parse_events
from .test_documents import MD, WordTokenizer, fake_embedder

ALICE, BOB = "alice@example.com", "bob@example.com"
SHARED_ID = 7


@pytest.fixture
def store():
    s = MemoryStore()
    s.chunks[SHARED_ID] = Chunk(SHARED_ID, "tutorial/cors.md", "CORS", "Use CORSMiddleware.")
    return s


@pytest.fixture
def provider():
    return RecordingProvider("Use a default [1].")


@pytest.fixture
def client(store, provider):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, similarity_threshold=0.5
    )
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([make_hit(1)])
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_chunk_tokenizer] = lambda: WordTokenizer
    with TestClient(app) as c:
        yield c


@pytest.fixture
def alice(store):
    return login(store, ALICE)


@pytest.fixture
def bob(store):
    return login(store, BOB)


def new_session(client, headers, title=None) -> dict:
    response = client.post(
        "/sessions", json={} if title is None else {"title": title}, headers=headers
    )
    assert response.status_code == 201
    return response.json()


def upload(client, headers, name="notes.md"):
    return client.post(
        "/documents", files={"file": (name, MD, "application/octet-stream")}, headers=headers
    )


# --- the Alice / Bob matrix ---------------------------------------------------------------


def test_bob_gets_404_on_every_route_of_alices_session(client, store, provider, alice, bob):
    sid = new_session(client, alice)["id"]
    client.post("/chat", json={"session_id": sid, "message": "hi"}, headers=alice)
    answer = next(m for m in store.messages[uuid.UUID(sid)] if m.role == "assistant")
    provider.calls.clear()
    before = len(store.messages[uuid.UUID(sid)])

    attempts = [
        client.get(f"/sessions/{sid}", headers=bob),
        client.patch(f"/sessions/{sid}", json={"title": "mine now"}, headers=bob),
        client.delete(f"/sessions/{sid}", headers=bob),
        client.get(f"/sessions/{sid}/messages", headers=bob),
        client.post("/chat", json={"session_id": sid, "message": "hi"}, headers=bob),
        client.post("/flashcards", json={"session_id": sid, "message_id": answer.id}, headers=bob),
    ]
    assert [r.status_code for r in attempts] == [404] * 6
    # Nothing happened to Alice's session: no LLM call, no new message, same title.
    assert provider.calls == []
    assert len(store.messages[uuid.UUID(sid)]) == before
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "hi"


def test_foreign_and_missing_session_look_exactly_the_same(client, alice, bob):
    sid = new_session(client, alice)["id"]
    missing = str(uuid.uuid4())
    for method, suffix in [("get", ""), ("delete", ""), ("get", "/messages")]:
        foreign = getattr(client, method)(f"/sessions/{sid}{suffix}", headers=bob)
        absent = getattr(client, method)(f"/sessions/{missing}{suffix}", headers=bob)
        assert (foreign.status_code, foreign.json()) == (absent.status_code, absent.json())


def test_bob_cannot_touch_alices_document_or_chunk(client, store, alice, bob):
    doc = upload(client, alice).json()
    (chunk_id,) = [i for i, o in store.chunk_owner.items() if o == user_id(store, ALICE)]

    assert client.delete(f"/documents/{doc['id']}", headers=bob).status_code == 404
    assert client.get(f"/chunks/{chunk_id}", headers=bob).status_code == 404
    # Both survived the attempt, and Alice still reads them.
    assert client.get(f"/chunks/{chunk_id}", headers=alice).status_code == 200
    assert [d["id"] for d in client.get("/documents", headers=alice).json()] == [doc["id"]]


def test_shared_chunk_is_readable_by_both(client, alice, bob):
    assert client.get(f"/chunks/{SHARED_ID}", headers=alice).status_code == 200
    assert client.get(f"/chunks/{SHARED_ID}", headers=bob).status_code == 200


def test_lists_show_only_own_rows(client, alice, bob):
    mine = new_session(client, alice, "alice's")
    theirs = new_session(client, bob, "bob's")
    upload(client, alice)

    assert [s["id"] for s in client.get("/sessions", headers=alice).json()["items"]] == [mine["id"]]
    assert [s["id"] for s in client.get("/sessions", headers=bob).json()["items"]] == [theirs["id"]]
    assert client.get("/documents", headers=bob).json() == []
    assert client.get("/sessions", headers=bob).json()["total"] == 1


def test_a_user_id_in_the_body_is_not_part_of_the_api(client, alice):
    sid = new_session(client, alice)["id"]
    extra = {"session_id": sid, "message": "hi", "owner_id": str(uuid.uuid4())}
    assert client.post("/chat", json=extra, headers=alice).status_code == 422
    extra = {"session_id": sid, "message_id": 1, "owner_id": str(uuid.uuid4())}
    assert client.post("/flashcards", json=extra, headers=alice).status_code == 422


def test_flashcards_work_for_the_owner(store, alice):
    """The positive case of the matrix: Alice's own answer and her own uploaded chunk."""
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_provider] = lambda: FakeProvider(
        json_responses=[
            json.dumps(
                {
                    "cards": [
                        {"question": f"Q{i}?", "answer": "A.", "source_chunk_id": SHARED_ID}
                        for i in range(3)
                    ]
                }
            )
        ]
    )
    sid = uuid.uuid4()
    login(store, ALICE, sessions=[sid])
    store.add_message(user_id(store, ALICE), sid, "user", "q")
    answer_id = store.add_message(
        user_id(store, ALICE), sid, "assistant", "a [1]", [{"id": SHARED_ID}]
    )
    with TestClient(app) as c:
        response = c.post(
            "/flashcards", json={"session_id": str(sid), "message_id": answer_id}, headers=alice
        )
    assert response.status_code == 200 and len(response.json()["cards"]) == 3


# --- the guard: a forgotten dependency fails the suite ------------------------------------

PUBLIC = {
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("GET", "/health"),
    ("GET", "/"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
    ("GET", "/docs/oauth2-redirect"),
}


def walk(routes):
    """Leaf routes as (method, path). Newer FastAPI wraps every included router in an
    `_IncludedRouter` that only yields its routes lazily, so a plain loop would see no
    /auth or /sessions routes and the guard would pass while checking nothing."""
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from walk(route.effective_route_contexts())
        elif hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def all_routes() -> set[tuple[str, str]]:
    return set(walk(app.routes))


def test_every_route_except_the_public_ones_needs_a_token(store):
    app.dependency_overrides[get_store] = lambda: store
    client = TestClient(app)  # no lifespan needed
    routes = all_routes()
    assert PUBLIC <= routes, "PUBLIC lists a route that no longer exists"
    # The walk must really reach nested routes; with fewer than this it checks nothing.
    assert {("POST", "/chat"), ("GET", "/sessions"), ("DELETE", "/auth/me")} <= routes

    for method, path in sorted(routes - PUBLIC):
        url = path.replace("{session_id}", str(uuid.uuid4())).replace("{chunk_id}", "1")
        url = url.replace("{document_id}", "1")
        assert "{" not in url, f"guard test does not know the parameter of {path}"
        response = client.request(method, url)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"


def test_old_api_key_header_alone_is_401(client):
    assert client.get("/sessions", headers={"X-API-Key": "anything"}).status_code == 401


# --- sessions CRUD ------------------------------------------------------------------------


def test_create_session_returns_201_with_a_server_made_id(client, alice):
    response = client.post("/sessions", json={}, headers=alice)
    body = response.json()
    assert response.status_code == 201
    assert set(body) == {"id", "title", "created_at", "updated_at"}
    assert body["title"] == DEFAULT_TITLE
    uuid.UUID(body["id"])
    # A client-chosen id is ignored (not even a field).
    chosen = str(uuid.uuid4())
    other = client.post("/sessions", json={"id": chosen, "title": "t"}, headers=alice).json()
    assert other["id"] != chosen and other["title"] == "t"


def test_get_rename_delete_roundtrip(client, store, alice):
    sid = new_session(client, alice)["id"]
    renamed = client.patch(f"/sessions/{sid}", json={"title": "  Biology  "}, headers=alice)
    assert renamed.status_code == 200 and renamed.json()["title"] == "Biology"
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "Biology"

    client.post("/chat", json={"session_id": sid, "message": "hi"}, headers=alice)
    assert client.delete(f"/sessions/{sid}", headers=alice).status_code == 204
    assert client.get(f"/sessions/{sid}", headers=alice).status_code == 404
    assert client.delete(f"/sessions/{sid}", headers=alice).status_code == 404
    assert uuid.UUID(sid) not in store.messages  # the messages went with it


@pytest.mark.parametrize("title", ["", "   ", "x" * 101])
def test_title_is_validated(client, alice, title):
    sid = new_session(client, alice)["id"]
    assert client.patch(f"/sessions/{sid}", json={"title": title}, headers=alice).status_code == 422
    assert client.post("/sessions", json={"title": title}, headers=alice).status_code == 422
    assert client.patch(f"/sessions/{sid}", json={}, headers=alice).status_code == 422
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == DEFAULT_TITLE


def test_title_of_exactly_100_characters_is_accepted(client, alice):
    sid = new_session(client, alice)["id"]
    assert (
        client.patch(f"/sessions/{sid}", json={"title": "x" * 100}, headers=alice).status_code
        == 200
    )


def test_session_id_must_be_a_uuid(client, alice):
    assert client.get("/sessions/nope", headers=alice).status_code == 422


# --- pagination ---------------------------------------------------------------------------


def test_pagination_total_next_limit_offset(client, alice):
    ids = [new_session(client, alice, f"s{i}")["id"] for i in range(5)]  # s4 is the newest

    first = client.get("/sessions?limit=2", headers=alice).json()
    assert [s["id"] for s in first["items"]] == [ids[4], ids[3]]
    assert (first["total"], first["limit"], first["offset"], first["next"]) == (5, 2, 0, 2)

    second = client.get("/sessions?limit=2&offset=2", headers=alice).json()
    assert [s["id"] for s in second["items"]] == [ids[2], ids[1]]
    assert second["next"] == 4

    last = client.get("/sessions?limit=2&offset=4", headers=alice).json()
    assert [s["id"] for s in last["items"]] == [ids[0]]
    assert last["next"] is None

    beyond = client.get("/sessions?limit=2&offset=10", headers=alice).json()
    assert beyond["items"] == [] and beyond["total"] == 5 and beyond["next"] is None
    exact = client.get("/sessions?limit=5", headers=alice).json()
    assert exact["next"] is None  # offset + limit == total: nothing follows


def test_defaults_are_limit_20_offset_0(client, alice):
    page = client.get("/sessions", headers=alice).json()
    assert (page["limit"], page["offset"], page["items"], page["total"]) == (20, 0, [], 0)


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
def test_bad_pagination_is_422(client, alice, query):
    assert client.get(f"/sessions?{query}", headers=alice).status_code == 422


def test_limit_100_is_the_maximum_allowed(client, alice):
    assert client.get("/sessions?limit=100", headers=alice).status_code == 200


def test_a_new_message_moves_the_session_to_the_top(client, alice):
    old = new_session(client, alice, "old")["id"]
    new_session(client, alice, "new")
    client.post("/chat", json={"session_id": old, "message": "bump"}, headers=alice)
    assert client.get("/sessions", headers=alice).json()["items"][0]["id"] == old


# --- auto-title ---------------------------------------------------------------------------


def test_first_user_message_becomes_the_title(client, alice):
    sid = new_session(client, alice)["id"]
    client.post("/chat", json={"session_id": sid, "message": "  What is\n  CORS?  "}, headers=alice)
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "What is CORS?"
    client.post("/chat", json={"session_id": sid, "message": "And another?"}, headers=alice)
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "What is CORS?"


def test_title_is_cut_to_60_characters(client, alice):
    sid = new_session(client, alice)["id"]
    client.post("/chat", json={"session_id": sid, "message": "q" * 500}, headers=alice)
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "q" * 60


def test_a_chosen_title_is_not_overwritten(client, alice):
    sid = new_session(client, alice, "My title")["id"]
    client.post("/chat", json={"session_id": sid, "message": "hello"}, headers=alice)
    assert client.get(f"/sessions/{sid}", headers=alice).json()["title"] == "My title"


def test_chat_does_not_create_sessions_any_more(client, store, alice):
    unknown = str(uuid.uuid4())
    response = client.post("/chat", json={"session_id": unknown, "message": "hi"}, headers=alice)
    assert response.status_code == 404
    assert store.sessions == {} or uuid.UUID(unknown) not in store.sessions


def test_chat_streams_for_the_owner(client, alice):
    sid = new_session(client, alice)["id"]
    response = client.post("/chat", json={"session_id": sid, "message": "hi"}, headers=alice)
    assert [name for name, _ in parse_events(response.text)][-1] == "done"


# --- DELETE /auth/me ----------------------------------------------------------------------


def test_deleting_the_account_removes_the_data_and_the_token(client, store, alice, bob):
    sid = new_session(client, alice)["id"]
    upload(client, alice)
    bob_session = new_session(client, bob)["id"]
    alice_id = user_id(store, ALICE)

    assert client.delete("/auth/me", headers=alice).status_code == 204

    assert client.get("/auth/me", headers=alice).status_code == 401  # the old token is dead
    assert client.get("/sessions", headers=alice).status_code == 401
    assert store.get_user(alice_id) is None
    assert uuid.UUID(sid) not in store.sessions and uuid.UUID(sid) not in store.messages
    assert store.documents == {} and alice_id not in store.chunk_owner.values()
    assert SHARED_ID in store.chunks  # shared knowledge stays
    assert client.get(f"/sessions/{bob_session}", headers=bob).status_code == 200  # Bob unaffected


def test_deleting_the_account_needs_a_token(client):
    assert client.delete("/auth/me").status_code == 401


# --- health -------------------------------------------------------------------------------


def test_health_needs_no_token_and_no_database(client):
    def broken_store():
        raise AssertionError("/health must not touch the store")

    app.dependency_overrides[get_store] = broken_store
    response = client.get("/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


# --- access log ---------------------------------------------------------------------------


def access_lines(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "mnemonic.access"]


def test_access_log_is_one_json_line_without_secrets(client, caplog, alice):
    token = alice["Authorization"].split()[1]
    sid = new_session(client, alice)["id"]
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="mnemonic.access"):
        client.get(f"/sessions/{sid}?secret_query=hunter2", headers=alice)
        client.post(
            "/auth/login", data={"username": "nobody@example.com", "password": "hunter2-password"}
        )
        client.get("/sessions")  # no token
    lines = access_lines(caplog)
    assert len(lines) == 3

    first = lines[0]
    assert set(first) == {"ts", "method", "path", "status", "duration_ms", "user_id", "ip"}
    assert first["path"] == "/sessions/{session_id}"  # the template, not the id
    assert (first["method"], first["status"]) == ("GET", 200)
    assert first["user_id"] and first["duration_ms"] >= 0
    assert lines[1]["path"] == "/auth/login" and lines[1]["user_id"] is None
    assert (lines[2]["status"], lines[2]["user_id"]) == (401, None)

    raw = "\n".join(r.getMessage() for r in caplog.records if r.name == "mnemonic.access")
    for secret in (token, "hunter2", "hunter2-password", "secret_query", sid, "Bearer"):
        assert secret not in raw
