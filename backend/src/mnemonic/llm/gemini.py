from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from mnemonic.llm.base import Usage
from mnemonic.schemas import Message


class GeminiProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def stream(
        self, messages: list[Message], usage: Usage | None = None
    ) -> AsyncIterator[str]:
        # Gemini takes the system prompt separately and calls the assistant "model".
        system = "\n".join(m.content for m in messages if m.role == "system")
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
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
