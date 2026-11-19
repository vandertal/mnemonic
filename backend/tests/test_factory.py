import pytest

from mnemonic.config import Settings
from mnemonic.llm.factory import build_provider, describe_provider
from mnemonic.llm.fake import FakeProvider
from mnemonic.llm.gemini import GeminiProvider


def make_settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_fake_provider_selected():
    assert isinstance(build_provider(make_settings(llm_provider="fake")), FakeProvider)


def test_gemini_provider_selected():
    settings = make_settings(llm_provider="gemini", gemini_api_key="k", gemini_model="m")
    assert isinstance(build_provider(settings), GeminiProvider)


def test_gemini_without_key_fails():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_provider(make_settings(llm_provider="gemini"))


def test_unknown_provider_fails():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        build_provider(make_settings(llm_provider="nope"))


def test_describe_provider_has_model_but_no_key():
    settings = make_settings(llm_provider="gemini", gemini_api_key="secret-key", gemini_model="m1")
    text = describe_provider(settings)
    assert "gemini" in text and "m1" in text
    assert "secret-key" not in text


def test_describe_provider_fake():
    assert describe_provider(make_settings(llm_provider="fake")) == "fake"
