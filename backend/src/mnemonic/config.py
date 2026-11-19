from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Shared secret the client must send in the X-API-Key header. The app refuses to start
    # without it, so a deploy can never be accidentally open to everyone.
    app_api_key: str = ""
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
