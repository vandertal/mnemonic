from mnemonic.config import Settings
from mnemonic.llm.base import LLMProvider
from mnemonic.llm.fake import FakeProvider
from mnemonic.llm.gemini import GeminiProvider


def build_provider(settings: Settings) -> LLMProvider:
    """Pick the LLM backend named by LLM_PROVIDER."""
    match settings.llm_provider:
        case "fake":
            return FakeProvider(delay=0.05)
        case "gemini":
            if not settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
            return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
        case other:
            raise ValueError(f"Unknown LLM_PROVIDER: {other!r}")


def model_name(settings: Settings) -> str:
    """Model recorded in the LLM call log."""
    return settings.gemini_model if settings.llm_provider == "gemini" else settings.llm_provider


def describe_provider(settings: Settings) -> str:
    """Human-readable provider + model for the startup log. Never includes the API key."""
    if settings.llm_provider == "gemini":
        return f"gemini (model: {settings.gemini_model})"
    return settings.llm_provider
