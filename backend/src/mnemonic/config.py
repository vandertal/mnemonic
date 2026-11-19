from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

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
