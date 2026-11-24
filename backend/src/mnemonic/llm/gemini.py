from collections.abc import AsyncIterator

from google import genai
from google.genai import types
from pydantic import BaseModel

from mnemonic.llm.base import Usage, parse_json_with_retry
from mnemonic.llm.errors import LLMBlocked
from mnemonic.schemas import Message, ToolCall, ToolSpec


def _split(messages: list[Message]) -> tuple[str, list[types.Content]]:
    """Gemini takes the system prompt separately and calls the assistant "model"."""
    system = "\n".join(m.content for m in messages if m.role == "system")
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":  # the tool result goes back as a function response of the user turn
            part = types.Part.from_function_response(
                name=m.tool_name or "", response={"result": m.content}
            )
            contents.append(types.Content(role="user", parts=[part]))
            continue
        parts = [types.Part(text=m.content)] if m.content else []
        if m.tool_call:
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(name=m.tool_call.name, args=m.tool_call.args),
                    thought_signature=m.tool_call.signature,
                )
            )
        contents.append(
            types.Content(role="model" if m.role == "assistant" else "user", parts=parts)
        )
    return system, contents


def response_schema(schema: type[BaseModel]) -> dict:
    """The Pydantic JSON schema without documentation-only keys. The SDK validates a schema
    strictly and rejects `examples` (added to our models for the OpenAPI docs) *before* any
    request is sent, which made every structured-output call fail."""

    def clean(node):
        if isinstance(node, dict):
            return {k: clean(v) for k, v in node.items() if k not in DOC_ONLY_KEYS}
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(schema.model_json_schema())


DOC_ONLY_KEYS = {"examples", "example"}


# finish_reason values that mean "the provider refused", not "the answer is complete".
_BLOCKED_REASONS = {
    "SAFETY",
    "PROHIBITED_CONTENT",
    "BLOCKLIST",
    "SPII",
    "RECITATION",
    "IMAGE_SAFETY",
}


def check_not_blocked(chunk: types.GenerateContentResponse) -> None:
    """Raise LLMBlocked when the prompt or the answer was stopped by the safety policy."""
    feedback = chunk.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        raise LLMBlocked(f"prompt blocked: {feedback.block_reason}")
    for candidate in chunk.candidates or []:
        reason = candidate.finish_reason
        if reason is not None and getattr(reason, "name", str(reason)) in _BLOCKED_REASONS:
            raise LLMBlocked(f"answer stopped: {getattr(reason, 'name', reason)}")


class GeminiProvider:
    supports_tools = True

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def stream_events(
        self, messages: list[Message], tools: list[ToolSpec], usage: Usage | None = None
    ) -> AsyncIterator[str | ToolCall]:
        """Function calling: text tokens as they come, and a ToolCall when the model asks."""
        system, contents = _split(messages)
        declarations = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters=t.parameters
            )
            for t in tools
        ]
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            # We run the loop ourselves (budget, logging, limits per round).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents, config=config
        )
        async for chunk in response:
            check_not_blocked(chunk)
            meta = chunk.usage_metadata
            if usage is not None and meta is not None:
                usage.tokens_in = meta.prompt_token_count
                usage.tokens_out = (meta.candidates_token_count or 0) + (
                    meta.thoughts_token_count or 0
                )
            for candidate in chunk.candidates or []:
                for part in (candidate.content.parts or []) if candidate.content else []:
                    if part.function_call and part.function_call.name:
                        yield ToolCall(
                            name=part.function_call.name,
                            args=dict(part.function_call.args or {}),
                            signature=part.thought_signature,
                        )
                    elif part.text and not part.thought:
                        yield part.text

    async def stream(
        self, messages: list[Message], usage: Usage | None = None
    ) -> AsyncIterator[str]:
        system, contents = _split(messages)
        config = types.GenerateContentConfig(system_instruction=system or None)
        response = await self._client.aio.models.generate_content_stream(
            model=self._model, contents=contents, config=config
        )
        async for chunk in response:
            check_not_blocked(chunk)
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
            response_json_schema=response_schema(schema),
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
