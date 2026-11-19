import asyncio
import json
import time
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from mnemonic.config import Settings, get_settings
from mnemonic.main import app, get_provider
from mnemonic.schemas import Message


class ScriptedProvider:
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        yield "Hello"
        yield " wor\nld"


class BrokenProvider:
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        yield "partial"
        raise RuntimeError("boom")


class HangingProvider:
    """Never sends a token — like a model stuck in an overloaded queue."""

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        await asyncio.Event().wait()
        yield "never"


class StallingProvider:
    """Sends one token, then goes silent."""

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        yield "first"
        await asyncio.Event().wait()


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, llm_timeout_seconds=0.2
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def parse_events(body: str) -> list[tuple[str, str]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = "message", ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        events.append((name, data))
    return events


def test_chat_streams_tokens_then_done(client):
    app.dependency_overrides[get_provider] = ScriptedProvider
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_events(response.text) == [
        ("message", "Hello"),
        ("message", " wor\nld"),
        ("done", ""),
    ]


def test_chat_reports_provider_failure_as_error_event(client):
    app.dependency_overrides[get_provider] = BrokenProvider
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    names = [name for name, _ in parse_events(response.text)]
    assert names == ["message", "error"]


def test_chat_times_out_when_model_never_answers(client):
    app.dependency_overrides[get_provider] = HangingProvider
    started = time.perf_counter()
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert time.perf_counter() - started < 2
    assert len(events := parse_events(response.text)) == 1
    name, text = events[0]
    assert name == "error"
    assert "did not respond within 0.2 seconds" in text


def test_chat_times_out_when_model_stalls_mid_answer(client):
    app.dependency_overrides[get_provider] = StallingProvider
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert [name for name, _ in parse_events(response.text)] == ["message", "error"]


def test_timeout_is_read_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "7.5")
    assert Settings(_env_file=None).llm_timeout_seconds == 7.5


@pytest.mark.parametrize(
    "body", [{}, {"messages": []}, {"messages": [{"role": "x", "content": "a"}]}]
)
def test_chat_rejects_invalid_body(client, body):
    app.dependency_overrides[get_provider] = ScriptedProvider
    assert client.post("/chat", json=body).status_code == 422
