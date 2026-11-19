from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "fake"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    # Max seconds to wait for the next token (the first one included) before giving up.
    llm_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
