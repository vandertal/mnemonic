from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from mnemonic.schemas import Message


class GeminiProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
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
            if chunk.text:
                yield chunk.text
