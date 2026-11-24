"""Classify provider failures, so the log, the admin stats and the user messages can tell
"the free quota is spent" from "the model is overloaded" from "the model refused".

Reads the SDK error by attribute (`.code`, the HTTP status) like retry.py does, so this module
needs no provider import."""

from mnemonic.llm.base import InvalidLLMOutput

QUOTA = "quota"  # 429: the (free-tier) rate or daily limit
OVERLOADED = "overloaded"  # 5xx: the provider is temporarily busy
BLOCKED = "blocked"  # safety filter / the model refused: a retry will not help
TIMEOUT = "timeout"  # nothing arrived within LLM_TIMEOUT_SECONDS
INVALID_OUTPUT = "invalid_output"  # structured output that does not match the schema
OTHER = "other"


class LLMBlocked(Exception):
    """The provider ended the answer because of its safety policy (not a transient failure)."""


def classify(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return TIMEOUT
    if isinstance(exc, LLMBlocked):
        return BLOCKED
    if isinstance(exc, InvalidLLMOutput):
        return INVALID_OUTPUT
    code = getattr(exc, "code", None)
    if code == 429:
        return QUOTA
    if isinstance(code, int) and code in (500, 502, 503, 504):
        return OVERLOADED
    return OTHER


# English sentences for the SSE `error` event and API details. The web shows its own localized
# text per kind; the bot shows these as they are.
MESSAGES = {
    QUOTA: "The AI service's free quota is used up for now. Please try again in a minute.",
    OVERLOADED: "The model is temporarily overloaded. Please try again in a moment.",
    BLOCKED: "The model declined to answer this question.",
    TIMEOUT: "The model did not respond in time. It may be overloaded: please try again.",
    INVALID_OUTPUT: "The model returned invalid output. Please try again.",
    OTHER: "The model failed to answer. Please try again.",
}
