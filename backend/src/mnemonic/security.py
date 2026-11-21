"""API-key gate and rate-limit dependencies for the protected endpoints."""

import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from mnemonic.config import Settings, get_settings
from mnemonic.limits import SlidingWindowLimiter, client_ip, retry_after_header

BUSY_MESSAGE = "The service is busy right now. Please try again in a minute."


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    # compare_digest takes the same time wherever the strings differ (no timing leak);
    # it needs bytes because str with non-ASCII characters raises TypeError.
    if (
        not settings.app_api_key
        or x_api_key is None
        or not secrets.compare_digest(x_api_key.encode(), settings.app_api_key.encode())
    ):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


@lru_cache
def get_ip_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(get_settings().rate_limit_per_minute)


@lru_cache
def get_global_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(get_settings().global_rpm)


@lru_cache
def get_auth_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(get_settings().auth_rate_limit_per_minute)


def limit_auth_per_ip(
    request: Request, limiter: Annotated[SlidingWindowLimiter, Depends(get_auth_limiter)]
) -> None:
    """Stricter per-IP limit for /auth/*: login guessing and argon2 are both worth throttling."""
    wait = limiter.acquire(client_ip(request))
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts from your address. Please slow down.",
            headers=retry_after_header(wait),
        )


def limit_per_ip(
    request: Request, limiter: Annotated[SlidingWindowLimiter, Depends(get_ip_limiter)]
) -> None:
    wait = limiter.acquire(client_ip(request))
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests from your address. Please slow down.",
            headers=retry_after_header(wait),
        )


def spend_llm_budget(limiter: SlidingWindowLimiter) -> None:
    """Take one slot of the service-wide LLM budget or raise 429 (call right before the LLM)."""
    wait = limiter.acquire("global")
    if wait is not None:
        raise HTTPException(status_code=429, detail=BUSY_MESSAGE, headers=retry_after_header(wait))
