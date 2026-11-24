import pytest

from mnemonic.limits import SlidingWindowLimiter
from mnemonic.main import app
from mnemonic.search_service import SearchService, get_search_service
from mnemonic.security import get_auth_limiter, get_global_limiter, get_ip_limiter

from .fakes import login as login_helper

TEST_JWT_SECRET = "test-secret-" + "x" * 32


@pytest.fixture(autouse=True)
def jwt_secret_env(monkeypatch):
    """Settings built in tests read the environment, so the lifespan's JWT_SECRET check passes."""
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)


@pytest.fixture(autouse=True)
def isolated_app_state():
    """Every test gets fresh, generous limiters (the real ones are process-wide singletons
    whose counts would leak between tests) and a clean override table."""
    app.dependency_overrides[get_ip_limiter] = lambda: SlidingWindowLimiter(1000)
    app.dependency_overrides[get_auth_limiter] = lambda: SlidingWindowLimiter(1000)
    app.dependency_overrides[get_global_limiter] = lambda: SlidingWindowLimiter(1000)
    # A fresh index per test (the real one is a process-wide singleton).
    service = SearchService()
    app.dependency_overrides[get_search_service] = lambda: service
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def login():
    """login(store, email="alice@example.com", sessions=[...]) -> {"Authorization": "Bearer ..."}"""
    return login_helper
