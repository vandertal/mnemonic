from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter
from mnemonic.main import app, get_store
from mnemonic.security import get_auth_limiter
from tests.conftest import TEST_JWT_SECRET
from tests.fakes import MemoryStore

EMAIL = "alice@example.com"
PASSWORD = "correct horse battery"


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


@pytest.fixture
def store():
    return MemoryStore()


def make_client(store, **kwargs):
    app.dependency_overrides[get_settings] = lambda: settings(**kwargs)
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


@pytest.fixture
def client(store):
    with make_client(store) as c:
        yield c


def register(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post("/auth/register", json={"email": email, "password": password, **extra})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/login", data={"username": email, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def token_for(client) -> str:
    register(client)
    return login(client).json()["access_token"]


# --- register ---------------------------------------------------------------------------


def test_register_returns_the_user_without_the_password(client):
    r = register(client)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "email", "created_at"}
    assert r.json()["email"] == EMAIL


def test_register_normalizes_the_email(client, store):
    assert register(client, email="  Alice@Example.COM ").json()["email"] == EMAIL
    assert store.get_user_by_email(EMAIL) is not None


def test_duplicate_email_is_409(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409


def test_duplicate_email_is_case_insensitive(client):
    assert register(client).status_code == 201
    assert register(client, email="ALICE@example.com").status_code == 409


def test_bad_email_is_422(client):
    assert register(client, email="not-an-email").status_code == 422


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_password_length_is_validated(client, password):
    assert register(client, password=password).status_code == 422


def test_stored_hash_is_argon2_and_not_the_password(client, store):
    register(client)
    _, stored = store.get_user_by_email(EMAIL)
    assert stored.startswith("$argon2")
    assert PASSWORD not in stored


# --- login ------------------------------------------------------------------------------


def test_login_returns_a_token_for_the_user(client):
    user_id = register(client).json()["id"]
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1440 * 60
    claims = jwt.decode(body["access_token"], TEST_JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == user_id


def test_wrong_password_and_unknown_email_give_the_same_401(client):
    register(client)
    wrong = login(client, password="wrong password!")
    unknown = login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.headers["www-authenticate"] == "Bearer"


# --- /auth/me ---------------------------------------------------------------------------


def test_me_returns_the_account(client):
    token = token_for(client)
    r = client.get("/auth/me", headers=bearer(token))
    assert r.status_code == 200
    assert r.json()["email"] == EMAIL


def forged(claims: dict, secret: str = TEST_JWT_SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, secret, algorithm=algorithm)


def assert_invalid(client, token: str | None):
    headers = bearer(token) if token else {}
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid or expired token"}
    assert r.headers["www-authenticate"] == "Bearer"


def test_me_without_a_token_is_401(client):
    assert_invalid(client, None)


def test_me_with_a_tampered_token_is_401(client):
    token = token_for(client)
    head, payload, signature = token.split(".")
    assert_invalid(client, f"{head}.{payload}.{signature[:-2]}AA")
    assert_invalid(client, forged({"sub": "x", "exp": 9999999999}, secret="y" * 40))


def test_me_with_an_expired_token_is_401(client):
    user_id = register(client).json()["id"]
    past = datetime.now(UTC) - timedelta(minutes=1)
    assert_invalid(client, forged({"sub": user_id, "exp": past}))


def test_me_with_an_alg_none_token_is_401(client):
    user_id = register(client).json()["id"]
    future = datetime.now(UTC) + timedelta(minutes=5)
    assert_invalid(client, jwt.encode({"sub": user_id, "exp": future}, key=None, algorithm="none"))


def test_me_with_a_token_without_exp_or_of_a_missing_user_is_401(client):
    user_id = register(client).json()["id"]
    assert_invalid(client, forged({"sub": user_id}))
    future = datetime.now(UTC) + timedelta(minutes=5)
    assert_invalid(client, forged({"sub": "00000000-0000-0000-0000-000000000000", "exp": future}))


# --- registration code ------------------------------------------------------------------


def test_registration_code_is_required_when_set(store):
    with make_client(store, registration_code="open-sesame") as c:
        assert register(c).status_code == 403
        assert register(c, registration_code="wrong").status_code == 403
        assert register(c, registration_code="open-sesame").status_code == 201


# --- rate limit -------------------------------------------------------------------------


def test_auth_endpoints_are_rate_limited_per_ip(store):
    with make_client(store) as c:
        limiter = SlidingWindowLimiter(2)
        app.dependency_overrides[get_auth_limiter] = lambda: limiter
        assert login(c).status_code == 401
        assert login(c).status_code == 401
        r = login(c)
        assert r.status_code == 429
        assert "retry-after" in r.headers


# --- startup ----------------------------------------------------------------------------


@pytest.mark.parametrize("secret", ["", "too-short"])
def test_app_refuses_to_start_without_a_strong_jwt_secret(store, secret):
    app.dependency_overrides[get_settings] = lambda: settings(jwt_secret=secret)
    with pytest.raises(RuntimeError, match="JWT_SECRET"), TestClient(app):
        pass
