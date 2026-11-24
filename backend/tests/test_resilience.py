"""LLM resilience: error classes, the single automatic retry, the non-English refusal, stats."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.language import is_non_english
from mnemonic.llm import errors as llm_errors
from mnemonic.llm import retry
from mnemonic.llm.base import InvalidLLMOutput
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.store import LLMCall

from .fakes import FakeRetriever, MemoryStore, login, make_hit

SESSION = uuid.UUID("44444444-4444-4444-4444-444444444444")


class Coded(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (Coded(429), "quota"),
        (Coded(503), "overloaded"),
        (Coded(500), "overloaded"),
        (Coded(400), "other"),
        (TimeoutError(), "timeout"),
        (TimeoutError(), "timeout"),
        (llm_errors.LLMBlocked("safety"), "blocked"),
        (InvalidLLMOutput("bad json"), "invalid_output"),
        (RuntimeError("boom"), "other"),
    ],
)
def test_provider_errors_are_classified(exc, kind):
    assert llm_errors.classify(exc) == kind


def test_every_class_has_a_user_sentence():
    for kind in ("quota", "overloaded", "blocked", "timeout", "invalid_output", "other"):
        assert llm_errors.MESSAGES[kind]


class Flaky:
    """Follows one script per stream() call: tokens and/or exceptions."""

    def __init__(self, *scripts: list) -> None:
        self.scripts = list(scripts)
        self.calls = 0

    async def stream(self, messages, usage=None):
        script = self.scripts[self.calls]
        self.calls += 1
        for item in script:
            if isinstance(item, Exception):
                raise item
            yield item


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store, monkeypatch):
    async def instant(seconds: float) -> None:
        return None

    monkeypatch.setattr(retry, "_sleep", instant)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, similarity_threshold=0.5
    )
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([make_hit(1)])
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app, headers=login(store, sessions=[SESSION])) as c:
        yield c
    app.dependency_overrides.clear()


def events_of(body: str) -> list[tuple[str, object]]:
    out = []
    for block in body.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        out.append((name, data))
    return out


def ask(client, text: str = "How do I enable CORS?"):
    return client.post("/chat", json={"session_id": str(SESSION), "message": text})


def test_a_failed_stream_is_retried_once_and_the_partial_text_is_discarded(client, store):
    provider = Flaky(["Half an ans", Coded(503)], ["The full answer."])
    app.dependency_overrides[get_provider] = lambda: provider
    events = events_of(ask(client).text)

    assert [n for n, _ in events] == ["message", "reset", "message", "sources", "done"]
    assert provider.calls == 2
    # The saved answer is only the second attempt: no half-answer glued to it.
    assert store.messages[SESSION][-1].content == "The full answer."
    assert [c.error_class for c in store.llm_calls] == ["overloaded", None]


def test_no_reset_when_nothing_was_sent_before_the_failure(client):
    provider = Flaky([RuntimeError("boom")], ["Fine."])
    app.dependency_overrides[get_provider] = lambda: provider
    assert [n for n, _ in events_of(ask(client).text)] == ["message", "sources", "done"]


def test_only_one_retry_then_the_final_error_with_its_class(client, store):
    provider = Flaky(["a", Coded(429)], ["b", Coded(429)], ["never reached"])
    app.dependency_overrides[get_provider] = lambda: provider
    events = events_of(ask(client).text)

    assert provider.calls == 2
    assert events[-1][0] == "error"
    assert events[-1][1]["kind"] == "quota"
    assert [c.error_class for c in store.llm_calls] == ["quota", "quota"]


def test_a_blocked_answer_is_not_retried(client):
    provider = Flaky(["x", llm_errors.LLMBlocked("safety")], ["never"])
    app.dependency_overrides[get_provider] = lambda: provider
    events = events_of(ask(client).text)

    assert provider.calls == 1
    assert events[-1][1]["kind"] == "blocked"


def test_admin_stats_count_failed_calls_by_class(store):
    for kind in ("quota", "quota", "overloaded", None):
        store.log_llm_call(
            LLMCall(SESSION, "m", 1, 1, 0.0, 1, "error" if kind else "ok", error_class=kind)
        )
    assert store.event_stats()["llm_errors_by_class"] == {"overloaded": 1, "quota": 2}


# ---------- E: non-English questions ----------


@pytest.mark.parametrize(
    "text",
    [
        "Как работает Depends в FastAPI?",
        "Як працює залежність у FastAPI?",
        "什么是依赖注入？",
        "كيف أستخدم FastAPI",
    ],
)
def test_foreign_scripts_are_detected(text):
    assert is_non_english(text)


@pytest.mark.parametrize(
    "text",
    [
        "How do I use Depends in FastAPI?",
        "What does `Депенденси` mean in `async def get_db(): yield db`?",  # code is ignored
        "Why does `Привет` break my code? I use async def and Depends(get_db)",
        "What is a naïve Bayes filter and the Zürich style guide?",
        "What does the word 数据 mean in my CSV header?",  # mostly English prose
        "ok",  # too short to judge
        "422?",
        "```python\nпеременная = 1\n```",
        "",
    ],
)
def test_english_and_code_are_not_flagged(text):
    assert not is_non_english(text)


def test_non_english_question_skips_retrieval_and_llm(client, store):
    class NoRetrieval:
        def __call__(self, *args, **kwargs):
            raise AssertionError("retrieval must not run")

    app.dependency_overrides[get_retriever] = lambda: NoRetrieval()
    provider = Flaky()  # no scripts: any call would fail
    app.dependency_overrides[get_provider] = lambda: provider
    events = events_of(ask(client, "Как включить CORS?").text)

    assert [n for n, _ in events] == ["message", "refusal", "done"]
    assert events[1][1] == {"reason": "non_english"}
    assert provider.calls == 0 and store.llm_calls == []
    answered = [p for n, _, p, _ in store.events if n == "question_answered"]
    assert answered[-1]["refused"] is True and answered[-1]["reason"] == "non_english"
    assert [m.role for m in store.messages[SESSION]] == ["user", "assistant"]
