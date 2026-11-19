from collections.abc import AsyncIterator

from google import genai
from google.genai import types
from pydantic import BaseModel

from mnemonic.llm.base import Usage, parse_json_with_retry
from mnemonic.schemas import Message


def _split(messages: list[Message]) -> tuple[str, list[types.Content]]:
    """Gemini takes the system prompt separately and calls the assistant "model"."""
    system = "\n".join(m.content for m in messages if m.role == "system")
    contents = [
        types.Content(
            role="model" if m.role == "assistant" else "user",
            parts=[types.Part(text=m.content)],
        )
        for m in messages
        if m.role != "system"
    ]
    return system, contents


class GeminiProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def stream(
        self, messages: list[Message], usage: Usage | None = None
    ) -> AsyncIterator[str]:
        system, contents = _split(messages)
        config = types.GenerateContentConfig(system_instruction=system or None)
        response = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents, config=config
        )
        async for chunk in response:
            meta = chunk.usage_metadata
            if usage is not None and meta is not None:
                # Counts are cumulative: the last chunk holds the totals. "Thinking" tokens
                # are billed as output, so they are added to it.
                usage.tokens_in = meta.prompt_token_count
                usage.tokens_out = (meta.candidates_token_count or 0) + (
                    meta.thoughts_token_count or 0
                )
            if chunk.text:
                yield chunk.text

    async def generate_json[T: BaseModel](
        self, messages: list[Message], schema: type[T], usage: Usage | None = None
    ) -> T:
        system, contents = _split(messages)
        # JSON mode + response_schema: the API constrains the output to the schema. We still
        # validate with Pydantic below (the constraint is not a guarantee for every field rule).
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            response_mime_type="application/json",
            response_schema=schema,
        )

        async def complete() -> str:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=contents, config=config
            )
            meta = response.usage_metadata
            if usage is not None and meta is not None:
                # Unlike stream(), a retry is a second paid call: the counts add up.
                usage.tokens_in = (usage.tokens_in or 0) + (meta.prompt_token_count or 0)
                usage.tokens_out = (
                    (usage.tokens_out or 0)
                    + (meta.candidates_token_count or 0)
                    + (meta.thoughts_token_count or 0)
                )
            return response.text or ""

        return await parse_json_with_retry(complete, schema)
