from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Secret that signs the access tokens (HS256). Required, >= 32 chars; whoever has it can
    # forge a login. Generate: uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = ""
    jwt_expire_minutes: int = 1440
    # If set, /auth/register needs this code (keeps strangers off the free LLM budget).
    registration_code: str = ""
    # Stricter per-IP limit for /auth/* (hashing is expensive, passwords can be guessed).
    auth_rate_limit_per_minute: int = 5
    # Per-IP limit (requests per minute) and the service-wide LLM budget (LLM calls per minute).
    # The free Gemini tier allows only a few calls per minute for the whole project.
    rate_limit_per_minute: int = 10
    global_rpm: int = 5

    # Price of one million tokens in USD, for the cost estimate in the LLM call log. Take the
    # numbers from the provider's pricing page; 0 (the free tier) logs a cost of 0.
    price_in_per_m: float = 0.0
    price_out_per_m: float = 0.0

    llm_provider: str = "fake"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    # Max seconds to wait for the next token (the first one included) before giving up.
    llm_timeout_seconds: float = 30.0
    # Postgres (Neon) connection string with the pgvector extension available.
    database_url: str = ""
    # RAG: how many chunks to retrieve, and the minimum cosine similarity of the best one.
    # Below the threshold the app answers "I don't know" without calling the LLM.
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.77
    # Which retriever feeds the chat: pgvector only (the original behaviour), the lexical BM25
    # index only, or both fused with Reciprocal Rank Fusion. See docs/decisions/0005.
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid"
    # How many candidates each retriever contributes to the fusion (the answer keeps top_k).
    retrieval_candidates: int = 20
    # Conversation memory: how many of the latest saved messages (user + assistant) go into the
    # prompt. Only complete question/answer pairs count, so an odd value rounds down.
    history_messages: int = 6
    # Uploads (M7a). Text-only PDFs: a scanned one has no text layer and is rejected.
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pdf_pages: int = 50
    max_documents_per_owner: int = 5
    # Comma-separated emails allowed to read GET /admin/stats (empty = nobody; the route is a 404).
    admin_emails: str = ""
    # Telegram bot (optional: without a token the webhook route answers 404 and nothing starts).
    # Token from @BotFather; the secret is any long random string; PUBLIC_URL is this service's
    # own https address (Render), used to register the webhook with Telegram at startup.
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    public_url: str = ""
    # Browser origins allowed to call the API (comma-separated). The default is the Vite dev server.
    cors_origins: str = "http://localhost:5173"


def admin_email_set(settings: Settings) -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
