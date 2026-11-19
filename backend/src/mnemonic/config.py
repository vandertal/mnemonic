from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "fake"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"


@lru_cache
def get_settings() -> Settings:
    return Settings()
