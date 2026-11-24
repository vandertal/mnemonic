import asyncio
import functools
import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.llm import retry
from mnemonic.llm.base import Usage
from mnemonic.llm.retry import stream_with_retry
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.schemas import Message

from .fakes import FakeRetriever, MemoryStore, login, make_hit
from .test_chat import parse_events

SESSION = uuid.UUID("33333333-3333-3333-3333-333333333333")
MESSAGES = [Message(role="user", content="q")]


class ProviderError(Exception):
    """Looks like the Gemini SDK's APIError: the HTTP status is in `.code`."""

    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code


class ScriptedProvider:
    """Each call to stream() follows the next script: a list of tokens and/or exceptions."""

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
def sleeps(monkeypatch):
    """Replace the backoff sleep: record the delays, don't wait."""
    recorded: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    monkeypatch.setattr(retry, "_sleep", fake_sleep)
    return recorded


async def collect(provider, on_retry=None) -> list[str]:
    return [t async for t in stream_with_retry(provider, MESSAGES, Usage(), on_retry)]


def sync(test):
    """Run an async test with asyncio.run (no pytest-asyncio: no new dependency)."""

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))

    return wrapper


# --- retry wrapper -----------------------------------------------------------------------


@sync
async def test_503_before_first_token_is_retried(sleeps):
    provider = ScriptedProvider([ProviderError(503)], [ProviderError(429)], ["Hel", "lo"])
    retries = []

    assert await collect(provider, lambda: retries.append(1)) == ["Hel", "lo"]
    assert provider.calls == 3 and len(retries) == 2
    # Exponential: 1s then 2s, each plus jitter below 0.5s.
    assert 1 <= sleeps[0] < 1.5 and 2 <= sleeps[1] < 2.5


@sync
async def test_gives_up_after_three_attempts(sleeps):
    provider = ScriptedProvider(*[[ProviderError(503)]] * 3)

    with pytest.raises(ProviderError):
        await collect(provider)
    assert provider.calls == 3 and len(sleeps) == 2


@sync
async def test_error_after_first_token_is_not_retried(sleeps):
    provider = ScriptedProvider(["Hel", ProviderError(503)], ["Hel", "lo"])
    received = []

    with pytest.raises(ProviderError):
        async for token in stream_with_retry(provider, MESSAGES, Usage()):
            received.append(token)
    assert received == ["Hel"]  # a retry would have repeated "Hel"
    assert provider.calls == 1 and sleeps == []


@pytest.mark.parametrize("error", [ProviderError(400), ProviderError(500), RuntimeError("boom")])
@sync
async def test_other_errors_are_not_retried(sleeps, error):
    provider = ScriptedProvider([error], ["never"])

    with pytest.raises(type(error)):
        await collect(provider)
    assert provider.calls == 1 and sleeps == []


# --- through /chat: retry and the LLM call log -------------------------------------------


def make_client(provider, **env):
    store = MemoryStore()
    settings = Settings(_env_file=None, similarity_threshold=0.5, **env)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever([make_hit(1)])
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app, headers=login(store, sessions=[SESSION])), store


def ask(client):
    return client.post("/chat", json={"session_id": str(SESSION), "message": "How do I use Query?"})


def test_chat_retries_503_before_first_token(sleeps):
    client, store = make_client(ScriptedProvider([ProviderError(503)], ["Fine ", "[1]"]))
    events = parse_events(ask(client).text)

    assert [name for name, _ in events] == ["message", "message", "sources", "done"]
    assert len(sleeps) == 1
    assert store.llm_calls[0].status.startswith("retried")


def test_stream_wrapper_does_not_retry_after_first_token_but_the_route_restarts_once(sleeps):
    # stream_with_retry itself never repeats after a token (it would duplicate text); the route
    # then makes ONE fresh attempt and tells the client to drop the partial text (`reset`).
    provider = ScriptedProvider(["part", ProviderError(503)], ["part", "ial"])
    client, store = make_client(provider)
    events = parse_events(ask(client).text)

    assert [name for name, _ in events] == [
        "message",
        "reset",
        "message",
        "message",
        "sources",
        "done",
    ]
    assert provider.calls == 2
    assert [c.status[:5] for c in store.llm_calls] == ["error", "ok+es"]  # both calls are logged
    assert [c.error_class for c in store.llm_calls] == ["overloaded", None]


def test_chat_error_after_exhausted_retries_is_logged_and_reported(sleeps):
    # 3 provider tries inside each of the 2 route attempts
    client, store = make_client(ScriptedProvider(*[[ProviderError(503)]] * 6))
    events = parse_events(ask(client).text)

    assert [name for name, _ in events] == ["error"]  # nothing was sent: no reset
    assert events[0][1]["kind"] == "overloaded"
    assert len(sleeps) == 2 + 1 + 2  # backoff, the pause before attempt 2, backoff
    assert [c.status for c in store.llm_calls] == ["error+est", "error+est"]


def test_llm_call_uses_provider_usage_and_prices(sleeps):
    class UsageProvider:
        async def stream(self, messages, usage=None):
            usage.tokens_in, usage.tokens_out = 1000, 200
            yield "Answer"

    client, store = make_client(UsageProvider(), price_in_per_m=0.5, price_out_per_m=2.0)
    ask(client)

    (call,) = store.llm_calls
    assert (call.tokens_in, call.tokens_out, call.status) == (1000, 200, "ok")  # not estimated
    assert call.cost_usd == pytest.approx((1000 * 0.5 + 200 * 2.0) / 1e6)
    assert call.session_id == SESSION and call.latency_ms >= 0


def test_llm_call_estimates_tokens_when_provider_reports_none(sleeps):
    client, store = make_client(ScriptedProvider(["x" * 40]), price_in_per_m=1.0)
    ask(client)

    (call,) = store.llm_calls
    assert call.tokens_out == 10  # 40 characters / 4
    assert call.tokens_in > 0 and call.status == "ok+est"


def test_log_failure_does_not_break_the_answer(sleeps):
    client, store = make_client(ScriptedProvider(["fine"]))

    def broken(call):
        raise RuntimeError("db down")

    store.log_llm_call = broken
    assert [n for n, _ in parse_events(ask(client).text)] == ["message", "sources", "done"]
