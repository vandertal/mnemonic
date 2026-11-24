import json
import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.llm.fake import FakeProvider
from mnemonic.main import app, get_provider, get_store
from mnemonic.store import Chunk

from .fakes import MemoryStore, login, user_id

SESSION = uuid.UUID("33333333-3333-3333-3333-333333333333")


def card(n: int, source: int | None) -> dict:
    return {"question": f"Q{n}?", "answer": f"A{n}.", "source_chunk_id": source}


def cards_json(*sources: int | None) -> str:
    return json.dumps({"cards": [card(i, s) for i, s in enumerate(sources, 1)]})


@pytest.fixture
def store():
    s = MemoryStore()
    s.chunks[1] = Chunk(1, "tutorial/cors.md", "CORS", "Use CORSMiddleware.")
    s.chunks[2] = Chunk(2, "tutorial/body.md", "Body", "Use a Pydantic model.")
    login(s, sessions=[SESSION])  # Alice owns the session
    alice = user_id(s)
    s.add_message(alice, SESSION, "user", "How do I enable CORS?")
    s.add_message(  # id 2: an answer that cites chunks 1 and 2
        alice,
        SESSION,
        "assistant",
        "Use CORSMiddleware [1] with a model [2].",
        [{"id": 1}, {"id": 2}],
    )
    s.add_message(alice, SESSION, "assistant", "I don't know: nothing relevant.", [])  # id 3
    return s


def make_client(store: MemoryStore, provider: FakeProvider):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_provider] = lambda: provider
    return TestClient(app, headers=login(store))


def post(client, message_id: int = 2):
    return client.post("/flashcards", json={"session_id": str(SESSION), "message_id": message_id})


def test_valid_set_is_returned_and_the_call_is_logged(store):
    provider = FakeProvider(json_responses=[cards_json(1, 2, None)])
    with make_client(store, provider) as client:
        response = post(client)
    assert response.status_code == 200
    cards = response.json()["cards"]
    assert [c["source_chunk_id"] for c in cards] == [1, 2, None]
    assert cards[0]["question"] == "Q1?"
    assert [c.status for c in store.llm_calls] == ["ok+est"]  # one row in llm_calls


def test_unknown_source_chunk_id_becomes_none(store):
    # 999 does not exist; 3 is not a source of THIS answer (a real chunk would not be allowed)
    store.chunks[3] = Chunk(3, "tutorial/other.md", "Other", "Unrelated.")
    provider = FakeProvider(json_responses=[cards_json(999, 3, 1)])
    with make_client(store, provider) as client:
        response = post(client)
    assert [c["source_chunk_id"] for c in response.json()["cards"]] == [None, None, 1]


def test_invalid_json_is_retried_once_then_502(store):
    provider = FakeProvider(json_responses=["not json at all", '{"cards": []}'])
    with make_client(store, provider) as client:
        response = post(client)
    assert response.status_code == 502
    assert "invalid output" in response.json()["detail"]
    assert store.llm_calls[0].error_class == "invalid_output"
    assert provider.json_calls == 2  # the first try + exactly one repeat
    assert [c.status for c in store.llm_calls] == ["error+est"]


def test_invalid_json_then_valid_json_succeeds(store):
    provider = FakeProvider(json_responses=["oops", cards_json(1, 1, 2)])
    with make_client(store, provider) as client:
        response = post(client)
    assert response.status_code == 200
    assert provider.json_calls == 2


def test_wrong_number_of_cards_is_invalid(store):
    provider = FakeProvider(json_responses=[cards_json(1, 2), cards_json(1, 2)])  # 2 < 3
    with make_client(store, provider) as client:
        assert post(client).status_code == 502


def test_unknown_message_is_404_and_answer_without_sources_is_422(store):
    with make_client(store, FakeProvider()) as client:
        assert post(client, message_id=99).status_code == 404
        assert post(client, message_id=1).status_code == 404  # a user message, not an answer
        assert post(client, message_id=3).status_code == 422


def test_requires_a_token(store):
    with make_client(store, FakeProvider()) as client:
        response = client.post(
            "/flashcards",
            json={"session_id": str(SESSION), "message_id": 2},
            headers={"Authorization": "Bearer nope"},
        )
    assert response.status_code == 401


def test_global_budget_is_spent(store):
    from mnemonic.limits import SlidingWindowLimiter
    from mnemonic.security import get_global_limiter

    limiter = SlidingWindowLimiter(1)
    app.dependency_overrides[get_global_limiter] = lambda: limiter
    with make_client(store, FakeProvider()) as client:
        assert post(client).status_code == 200
        second = post(client)
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) >= 1
