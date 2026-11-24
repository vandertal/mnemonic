from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ToolSpec(BaseModel):
    """A tool offered to the model: name, description and a JSON-schema of its arguments."""

    name: str
    description: str
    parameters: dict


class ToolCall(BaseModel):
    """The model asks the server to run a tool. `signature` is opaque provider data that must
    be sent back with the call (Gemini "thought signatures")."""

    name: str
    args: dict = Field(default_factory=dict)
    signature: bytes | None = None


class Message(BaseModel):
    """Internal message passed to LLM providers. Only the server creates `system` and `tool`
    ones (and assistant messages with a `tool_call`); the client cannot, see ClientMessage."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_call: ToolCall | None = None  # assistant: the call it made
    tool_name: str | None = None  # tool: which tool produced `content`


class ClientMessage(BaseModel):
    """What the client may send: no `system` role, so it cannot touch the system prompt."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


EXAMPLE_SESSION_ID = "3f2b8c1e-5a47-4d0e-9c1b-7e6a2d4f8b90"
EXAMPLE_TIME = "2026-11-21T10:15:00Z"
EXAMPLE_SESSION = {
    "id": EXAMPLE_SESSION_ID,
    "title": "FastAPI basics",
    "created_at": EXAMPLE_TIME,
    "updated_at": EXAMPLE_TIME,
}


class ChatRequest(BaseModel):
    """One user turn. The client sends only its session id and the question: there is no
    field through which a `system` message (or a fake assistant turn) could get in. The user
    comes from the Bearer token, never from the body."""

    model_config = ConfigDict(
        extra="forbid",  # an old-style `messages` list or `owner_id` -> 422
        json_schema_extra={
            "examples": [
                {"session_id": EXAMPLE_SESSION_ID, "message": "How do I declare a query parameter?"}
            ]
        },
    )

    session_id: UUID = Field(description="A session of the caller, from `POST /sessions`.")
    message: str = Field(min_length=1, max_length=2000)


class Flashcard(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    # Which retrieved chunk the card comes from; the server nulls ids it cannot verify.
    source_chunk_id: int | None = None


class FlashcardSet(BaseModel):
    """What the model must return: 3-5 cards. Also sent to the client as is."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "cards": [
                        {
                            "question": "How do you make a query parameter optional?",
                            "answer": "Give it a default, e.g. `q: str | None = None`.",
                            "source_chunk_id": 1042,
                        },
                        {
                            "question": "Where do query parameters appear in a URL?",
                            "answer": "After the `?`, as `key=value` pairs separated by `&`.",
                            "source_chunk_id": 1042,
                        },
                        {
                            "question": "What happens when a query parameter has the wrong type?",
                            "answer": "FastAPI answers 422 and describes the error.",
                            "source_chunk_id": None,
                        },
                    ]
                }
            ]
        }
    )

    cards: list[Flashcard] = Field(min_length=3, max_length=5)


class FlashcardRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"session_id": EXAMPLE_SESSION_ID, "message_id": 42}]},
    )

    session_id: UUID = Field(description="A session of the caller.")
    message_id: int = Field(ge=1, description="Id of an assistant message in this session.")


class SessionCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True, json_schema_extra={"examples": [{"title": "FastAPI basics"}]}
    )

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional. Default: 'New chat', replaced by the first question.",
    )


class SessionUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"title": "Dependency injection"}]},
    )

    title: str = Field(min_length=1, max_length=100)


class SessionOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [EXAMPLE_SESSION]})

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SessionPage(BaseModel):
    """Offset pagination. `next` is the offset of the next page, null on the last one."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"items": [EXAMPLE_SESSION], "total": 41, "limit": 20, "offset": 0, "next": 20}
            ]
        }
    )

    items: list[SessionOut]
    total: int
    limit: int
    offset: int
    next: int | None


class MessageOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 42,
                    "role": "assistant",
                    "content": "Declare it as a function argument [1].",
                    "sources": [
                        {
                            "id": 1042,
                            "file_path": "tutorial/query-params.md",
                            "heading": "Query Parameters",
                            "similarity": 0.83,
                        }
                    ],
                    "created_at": EXAMPLE_TIME,
                }
            ]
        }
    )

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict] | None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"id": 7, "filename": "notes.md", "chunks": 12, "created_at": EXAMPLE_TIME}
            ]
        }
    )

    id: int
    filename: str
    chunks: int
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1042,
                    "file": "tutorial/query-params.md",
                    "heading": "Query Parameters",
                    "content": "When you declare other function parameters...",
                }
            ]
        }
    )

    id: int
    file: str
    heading: str
    content: str


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"email": "alice@example.com", "password": "correct horse battery"}]
        }
    )

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    registration_code: str | None = Field(
        default=None, description="Required only if the server sets REGISTRATION_CODE."
    )


class UserOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "b1c5f0aa-2d5e-4c34-8a53-0b6f3c9d7e11",
                    "email": "alice@example.com",
                    "created_at": EXAMPLE_TIME,
                }
            ]
        }
    )

    id: UUID
    email: str
    created_at: datetime


class TokenOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "expires_in": 86400,
                }
            ]
        }
    )

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds.")


class SnippetOut(BaseModel):
    """Plain text plus highlight offsets INTO that text. Never HTML: the client draws the marks,
    so nothing inside an uploaded document can inject markup."""

    text: str
    highlights: list[tuple[int, int]] = Field(
        description="[start, end) character offsets of matched words inside `text`."
    )


class SearchHitOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chunk_id": 42,
                    "document": "tutorial/cors.md",
                    "heading": "CORS (Cross-Origin Resource Sharing)",
                    "score": 7.31,
                    "snippet": {
                        "text": "You can configure it in your FastAPI application using the "
                        "CORSMiddleware.",
                        "highlights": [[63, 75]],
                    },
                    "matched_terms": ["cors"],
                }
            ]
        }
    )

    chunk_id: int
    document: str = Field(description="The file the chunk comes from.")
    heading: str
    score: float = Field(
        description="Ranker score; higher is better, not comparable across queries."
    )
    snippet: SnippetOut
    matched_terms: list[str]


class TermExplanationOut(BaseModel):
    term: str
    tf: int = Field(description="Times the term occurs in this chunk.")
    df: int = Field(description="Chunks that contain the term.")
    idf: float = Field(description="Rarity weight: higher for rarer terms.")
    contribution: float = Field(description="What this term adds to the score.")


class ExplainOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chunk_id": 42,
                    "document": "tutorial/cors.md",
                    "ranker": "bm25",
                    "n_docs": 1523,
                    "avgdl": 118.4,
                    "doc_length": 96,
                    "terms": [{"term": "cors", "tf": 4, "df": 9, "idf": 5.1, "contribution": 7.31}],
                    "score": 7.31,
                }
            ]
        }
    )

    chunk_id: int
    document: str
    ranker: Literal["bm25", "tfidf"]
    n_docs: int = Field(description="Chunks in the index.")
    avgdl: float = Field(description="Average chunk length in indexed words.")
    doc_length: int = Field(description="Length of this chunk in indexed words.")
    terms: list[TermExplanationOut]
    score: float = Field(description="Sum of the contributions.")
