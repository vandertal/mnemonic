import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.main import app, get_store
from mnemonic.store import Chunk

from .fakes import MemoryStore, login


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def auth(store):
    return login(store)


@pytest.fixture
def client(store):
    store.chunks[7] = Chunk(7, "tutorial/cors.md", "CORS > Origins", "Use CORSMiddleware.")
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_chunk_found(client, auth):
    response = client.get("/chunks/7", headers=auth)
    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "file": "tutorial/cors.md",
        "heading": "CORS > Origins",
        "content": "Use CORSMiddleware.",
    }


def test_chunk_not_found(client, auth):
    assert client.get("/chunks/8", headers=auth).status_code == 404


def test_chunk_requires_a_token(client):
    assert client.get("/chunks/7").status_code == 401
    assert client.get("/chunks/7", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_chunk_id_must_be_a_valid_integer(client, auth):
    assert client.get("/chunks/abc", headers=auth).status_code == 422
    assert client.get("/chunks/99999999999999999999", headers=auth).status_code == 422
