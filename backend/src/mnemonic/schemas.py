from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class Message(BaseModel):
    """Internal message passed to LLM providers. Only the server creates `system` ones."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ClientMessage(BaseModel):
    """What the client may send: no `system` role, so it cannot touch the system prompt."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ClientMessage] = Field(min_length=1)

    @model_validator(mode="after")
    def last_message_is_question(self) -> Self:
        if self.messages[-1].role != "user":
            raise ValueError("the last message must come from the user")
        return self
