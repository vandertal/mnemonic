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
