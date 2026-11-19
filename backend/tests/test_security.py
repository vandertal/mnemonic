import uuid

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.main import app, get_provider, get_retriever, get_store
from mnemonic.rag import REFUSAL
from mnemonic.security import BUSY_MESSAGE, get_global_limiter, get_ip_limiter

from .fakes import AUTH, KEY, FakeRetriever, MemoryStore, RecordingProvider, make_hit

SESSION = uuid.UUID("22222222-2222-2222-2222-222222222222")
BODY = {"session_id": str(SESSION), "message": "How do I use Query?"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_client(hits=None, **env):
    """TestClient with a fake retriever/provider/store. Returns (client, provider, store)."""
    provider, store = RecordingProvider("ok"), MemoryStore()
    settings = Settings(_env_file=None, app_api_key=KEY, similarity_threshold=0.5, **env)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_retriever] = lambda: FakeRetriever(hits or [make_hit(1)])
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app), provider, store


def use_limiter(dependency, limit: int) -> SlidingWindowLimiter:
    """Install ONE limiter instance (a bare lambda would build a fresh, empty one per request)."""
    limiter = SlidingWindowLimiter(limit)
    app.dependency_overrides[dependency] = lambda: limiter
    return limiter


# --- API key -----------------------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}])
def test_chat_without_valid_key_is_401(headers):
    client, provider, store = make_client()
    response = client.post("/chat", json=BODY, headers=headers)

    assert response.status_code == 401
    assert provider.calls == [] and store.messages == {}


def test_history_without_valid_key_is_401():
    client, _, _ = make_client()
    url = f"/sessions/{SESSION}/messages"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get(url, headers=AUTH).status_code == 200


def test_valid_key_is_accepted_and_index_needs_no_key():
    client, _, _ = make_client()
    assert client.post("/chat", json=BODY, headers=AUTH).status_code == 200
    assert client.get("/").status_code == 200


def test_unauthenticated_request_does_not_consume_the_ip_limit():
    client, _, _ = make_client()
    use_limiter(get_ip_limiter, 1)
    for _ in range(3):
        assert client.post("/chat", json=BODY).status_code == 401
    assert client.post("/chat", json=BODY, headers=AUTH).status_code == 200


def test_app_refuses_to_start_without_api_key():
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, app_api_key="")
    with pytest.raises(RuntimeError, match="APP_API_KEY"), TestClient(app):
        pass


def test_empty_configured_key_never_matches_an_empty_header():
    client, _, _ = make_client()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, app_api_key="")
    assert client.post("/chat", json=BODY, headers={"X-API-Key": ""}).status_code == 401


# --- per-IP limit ------------------------------------------------------------------------


def test_per_ip_limit_returns_429_with_retry_after():
    client, _, _ = make_client()
    use_limiter(get_ip_limiter, 2)
    codes = [client.post("/chat", json=BODY, headers=AUTH) for _ in range(3)]

    assert [r.status_code for r in codes] == [200, 200, 429]
    assert int(codes[2].headers["Retry-After"]) >= 1


def test_per_ip_limit_is_per_first_forwarded_address():
    client, _, _ = make_client()
    use_limiter(get_ip_limiter, 1)

    def post(forwarded):
        return client.post("/chat", json=BODY, headers=AUTH | {"X-Forwarded-For": forwarded})

    assert post("1.1.1.1, 10.0.0.1").status_code == 200
    assert post("1.1.1.1, 10.0.0.2").status_code == 429  # same first element: same client
    assert post("2.2.2.2, 10.0.0.1").status_code == 200  # another client


# --- global LLM budget -------------------------------------------------------------------


def test_global_limit_returns_429_and_the_llm_is_not_called():
    client, provider, store = make_client()
    use_limiter(get_global_limiter, 1)
    first = client.post("/chat", json=BODY, headers=AUTH)
    second = client.post("/chat", json=BODY, headers=AUTH)

    assert first.status_code == 200 and second.status_code == 429
    assert second.json()["detail"] == BUSY_MESSAGE
    assert int(second.headers["Retry-After"]) >= 1
    assert len(provider.calls) == 1
    # The rejected request saved nothing, so a retry will not duplicate the question.
    assert [m.role for m in store.messages[SESSION]] == ["user", "assistant"]


def test_i_dont_know_does_not_spend_the_global_budget():
    client, provider, _ = make_client(hits=[make_hit(1, similarity=0.1)])
    limiter = SlidingWindowLimiter(1)
    app.dependency_overrides[get_global_limiter] = lambda: limiter

    for _ in range(3):
        response = client.post("/chat", json=BODY, headers=AUTH)
        assert response.status_code == 200 and REFUSAL in response.text
    assert provider.calls == []
    assert limiter.acquire("global") is None  # the single slot is still free


# --- the limiter itself ------------------------------------------------------------------


def test_window_slides_and_retry_after_points_to_the_oldest_hit():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, window=60, clock=clock)

    assert limiter.acquire("a") is None  # t=1000
    clock.now += 10
    assert limiter.acquire("a") is None  # t=1010
    clock.now += 10
    assert limiter.acquire("a") == pytest.approx(40)  # oldest (1000) expires at 1060, now 1020
    assert limiter.acquire("b") is None  # keys are independent
    clock.now = 1060
    assert limiter.acquire("a") is None  # 1000 slid out of the window; 1010 is still in
    assert limiter.acquire("a") == pytest.approx(10)  # 1010 and 1060 are in the window


def test_rejected_hits_are_not_recorded():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, window=60, clock=clock)
    limiter.acquire("a")
    for _ in range(5):
        clock.now += 1
        assert limiter.acquire("a") is not None
    clock.now = 1060
    assert limiter.acquire("a") is None  # hammering did not extend the ban


def test_expired_keys_are_swept_when_too_many(monkeypatch):
    monkeypatch.setattr("mnemonic.limits.MAX_KEYS", 3)
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, window=60, clock=clock)
    for i in range(4):
        limiter.acquire(str(i))
    clock.now += 61
    limiter.acquire("new")
    assert list(limiter._hits) == ["new"]
