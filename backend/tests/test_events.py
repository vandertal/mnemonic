"""Product events and GET /admin/stats: what is recorded, what never is, who may read it."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.store import Chunk, LLMCall

from .fakes import FakeRetriever, MemoryStore, RecordingProvider, login, make_hit, user_id

SESSION = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADMIN = "owner@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
def store():
    return MemoryStore()


def make_client(store, hits=None, answer="Use it [1]."):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, similarity_threshold=0.5, admin_emails=ADMIN
    )
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(
        [make_hit(1)] if hits is None else hits
    )
    app.dependency_overrides[get_provider] = lambda: RecordingProvider(answer)
    return TestClient(app)


def ask(client, text="How do I enable CORS?"):
    return client.post("/chat", json={"session_id": str(SESSION), "message": text})


def test_signup_is_recorded(store):
    with make_client(store) as client:
        r = client.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    assert r.status_code == 201
    assert store.events[0][:2] == ("signup", uuid.UUID(r.json()["id"]))


def test_cited_answer_is_recorded_without_the_question_text(store):
    secret = "my very private question about CORS"
    with make_client(store) as client:
        client.headers.update(login(store, sessions=[SESSION]))
        assert ask(client, secret).status_code == 200
    name, uid, props, _ = store.events[0]
    assert name == "question_answered"
    assert uid == user_id(store)
    assert props == {"cited": True, "refused": False}
    assert secret not in repr(store.events)


def test_refusal_is_recorded_as_refused(store):
    with make_client(store, hits=[make_hit(1, similarity=0.1)]) as client:
        client.headers.update(login(store, sessions=[SESSION]))
        ask(client)
    assert store.events[0][2] == {"cited": False, "refused": True}


def test_answer_without_citations_is_not_cited(store):
    with make_client(store, answer="No markers here.") as client:
        client.headers.update(login(store, sessions=[SESSION]))
        ask(client)
    assert store.events[0][2] == {"cited": False, "refused": False}


def test_a_broken_events_table_does_not_break_signup_or_chat(store):
    store.fail_events = True
    with make_client(store) as client:
        r = client.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
        assert r.status_code == 201
        client.headers.update(login(store, sessions=[SESSION]))
        response = ask(client)
    assert response.status_code == 200
    assert "event: done" in response.text
    assert store.events == []


def test_cards_made_is_recorded(store):
    store.chunks[1] = Chunk(1, "tutorial/cors.md", "CORS", "Use CORSMiddleware.")
    headers = login(store, sessions=[SESSION])
    alice = user_id(store)
    store.add_message(alice, SESSION, "user", "q")
    mid = store.add_message(alice, SESSION, "assistant", "Use it [1].", [{"id": 1}])
    cards = [{"question": f"Q{i}?", "answer": "A.", "source_chunk_id": 1} for i in range(3)]
    provider = FakeProvider(json_responses=[json.dumps({"cards": cards})])
    with make_client(store) as client:
        app.dependency_overrides[get_provider] = lambda: provider
        client.headers.update(headers)
        r = client.post("/flashcards", json={"session_id": str(SESSION), "message_id": mid})
    assert r.status_code == 200
    assert [e[0] for e in store.events] == ["cards_made"]


def test_search_is_recorded(store):
    with make_client(store) as client:
        client.headers.update(login(store))
        r = client.get("/search", params={"q": "cors"})
    assert r.status_code == 200  # an empty index still answers; no results
    assert store.events[0][0] == "search"
    assert store.events[0][2] == {"results": False}


def test_stats_are_hidden_from_everyone_but_admins(store):
    with make_client(store) as client:
        assert client.get("/admin/stats").status_code == 401  # no token
        client.headers.update(login(store, "student@example.com"))
        assert client.get("/admin/stats").status_code == 404  # logged in, not an admin
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)  # ADMIN_EMAILS empty
    with TestClient(app, headers=login(store, ADMIN)) as client:
        assert client.get("/admin/stats").status_code == 404


def test_stats_numbers(store):
    login(store, "alice@example.com")
    login(store, "bob@example.com")
    login(store, "carol@example.com")  # registered, never asked anything
    a, b = user_id(store, "alice@example.com"), user_id(store, "bob@example.com")
    for uid in (a, b):
        store.log_event("signup", uid, {})
    store.log_event("question_answered", a, {"cited": True, "refused": False})
    store.log_event("question_answered", a, {"cited": True, "refused": False})
    store.log_event("question_answered", b, {"cited": False, "refused": True})
    store.log_event("search", b, {"results": True})
    store.log_llm_call(LLMCall(SESSION, "m", 10, 10, 0.02, 100, "ok"))

    with make_client(store) as client:
        client.headers.update(login(store, ADMIN))
        body = client.get("/admin/stats").json()

    assert body["totals"] == {"signup": 2, "question_answered": 3, "cards_made": 0, "search": 1}
    assert body["distinct_users"] == 2
    assert body["registered_users"] == 4  # alice, bob, carol and the admin
    assert len(body["last_days"]) == 7
    assert body["last_days"][-1]["question_answered"] == 3  # today is the last entry
    assert body["last_days"][0]["question_answered"] == 0
    assert body["main_action"]["users"] == 1  # only alice got a cited answer
    assert body["main_action"]["rate"] == 0.25
    assert body["llm_cost"] == {
        "total_usd": 0.02,
        "calls": 1,
        "active_users": 2,
        "avg_per_active_user_usd": 0.01,
    }
