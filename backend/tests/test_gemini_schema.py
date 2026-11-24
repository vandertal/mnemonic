"""Regression: every structured-output (flashcards) call failed before reaching Gemini.

FlashcardSet carries `examples` for the OpenAPI docs. The SDK turned the Pydantic model into its
own strict Schema and raised "examples: Extra inputs are not permitted" locally, so the route
answered 502 every time. The provider now sends a cleaned JSON schema."""

import asyncio
import json
from types import SimpleNamespace

from mnemonic.llm.gemini import GeminiProvider, response_schema
from mnemonic.schemas import FlashcardSet, Message


def keys(node) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in keys(v)}
    return set()


def test_the_response_schema_has_no_documentation_only_keys():
    assert "examples" in keys(FlashcardSet.model_json_schema())  # the trigger is real
    assert "examples" not in keys(response_schema(FlashcardSet))


def test_generate_json_builds_a_request_the_sdk_accepts():
    sent = {}
    cards = {
        "cards": [
            {"question": f"Q{i}?", "answer": f"A{i}.", "source_chunk_id": 1} for i in range(3)
        ]
    }

    async def generate_content(*, model, contents, config):
        sent["config"] = config  # the SDK validated it when we built it
        return SimpleNamespace(text=json.dumps(cards), usage_metadata=None)

    provider = GeminiProvider("test-key", "test-model")
    provider._client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    messages = [Message(role="system", content="s"), Message(role="user", content="u")]
    result = asyncio.run(provider.generate_json(messages, FlashcardSet))

    assert len(result.cards) == 3
    assert sent["config"].response_mime_type == "application/json"
    assert "examples" not in keys(sent["config"].response_json_schema)
