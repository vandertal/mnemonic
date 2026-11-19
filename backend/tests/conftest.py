import pytest

from mnemonic.limits import SlidingWindowLimiter
from mnemonic.main import app
from mnemonic.security import get_global_limiter, get_ip_limiter


@pytest.fixture(autouse=True)
def isolated_app_state():
    """Every test gets fresh, generous limiters (the real ones are process-wide singletons
    whose counts would leak between tests) and a clean override table."""
    app.dependency_overrides[get_ip_limiter] = lambda: SlidingWindowLimiter(1000)
    app.dependency_overrides[get_global_limiter] = lambda: SlidingWindowLimiter(1000)
    yield
    app.dependency_overrides.clear()
