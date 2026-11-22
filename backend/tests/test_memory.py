import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.rag import select_history
from mnemonic.store import StoredMessage

from .fakes import FakeRetriever, MemoryStore, RecordingProvider, login, make_hit, user_id

SESSION = uuid.UUID("22222222-2222-2222-2222-222222222222")


def msg(role: str, content: str) -> StoredMessage:
    return StoredMessage(role, content, None, datetime.now(UTC))  # type: ignore[arg-type]


def texts(history) -> list[str]:
    return [m.content for m in history]


def test_history_keeps_only_complete_pairs():
    stored = [
        msg("user", "q1"),
        msg("assistant", "a1"),
        msg("user", "q2 failed"),  # no answer: the LLM errored
        msg("user", "q3"),
        msg("assistant", "a3"),
        msg("user", "q4 trailing"),  # no answer yet
    ]
    assert texts(select_history(stored, 6)) == ["q1", "a1", "q3", "a3"]


def test_history_is_cut_to_the_last_n_messages():
    stored = []
    for i in range(1, 6):
        stored += [msg("user", f"q{i}"), msg("assistant", f"a{i}")]
    assert texts(select_history(stored, 4)) == ["q4", "a4", "q5", "a5"]
    assert texts(select_history(stored, 5)) == ["q4", "a4", "q5", "a5"]  # odd N rounds down
    assert select_history(stored, 0) == []
    assert select_history(stored, 1) == []


@pytest.fixture
def setup():
    store, provider, retriever = (
        MemoryStore(),
        RecordingProvider("Yes [1]."),
        FakeRetriever([make_hit(1)]),
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, similarity_threshold=0.5, history_messages=6
    )
    app.dependency_overrides[get_retriever] = lambda: retriever
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app, headers=login(store, sessions=[SESSION])) as client:
        yield client, store, provider, retriever
    app.dependency_overrides.clear()


def test_chat_prompt_contains_last_pairs_and_current_question(setup):
    client, store, provider, retriever = setup
    for i in range(1, 6):  # 5 complete pairs: only the last 3 may reach the prompt
        store.add_message(user_id(store), SESSION, "user", f"q{i}")
        store.add_message(user_id(store), SESSION, "assistant", f"a{i}")
    store.add_message(user_id(store), SESSION, "user", "unanswered")  # trailing: ignored

    response = client.post("/chat", json={"session_id": str(SESSION), "message": "now"})
    assert response.status_code == 200

    sent = provider.calls[0]
    assert [m.role for m in sent] == ["system"] + ["user", "assistant"] * 3 + ["user"]
    assert [m.content for m in sent[1:]] == ["q3", "a3", "q4", "a4", "q5", "a5", "now"]
    assert sum(m.role == "system" for m in sent) == 1  # the system message stays server-only
    assert retriever.questions == ["now"]  # retrieval looks only at the current question
