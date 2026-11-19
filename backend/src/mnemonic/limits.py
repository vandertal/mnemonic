"""In-memory sliding-window rate limiter (no dependencies, single process only)."""

import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

# Above this many tracked keys, expired ones are swept out (keeps memory bounded when
# someone sends requests with many different, possibly forged, IPs).
MAX_KEYS = 10_000


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window` seconds for each key.

    Per key we keep a deque of the timestamps of recent hits. A new hit first drops the
    timestamps older than the window, then is allowed only if fewer than `limit` remain.
    Unlike a fixed "per calendar minute" counter there is no burst at the minute boundary.
    State lives in this process: with several workers/instances every one has its own counts.
    """

    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def acquire(self, key: str) -> float | None:
        """Record a hit. Returns None if allowed, else the seconds to wait before retrying."""
        now = self._clock()
        if len(self._hits) > MAX_KEYS:
            self._sweep(now)
        hits = self._hits.setdefault(key, deque())
        self._prune(hits, now)
        if len(hits) >= self.limit:
            return max(hits[0] + self.window - now, 0.0)  # when the oldest hit expires
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        for key in list(self._hits):
            self._prune(self._hits[key], now)
            if not self._hits[key]:
                del self._hits[key]


def retry_after_header(seconds: float) -> dict[str, str]:
    """`Retry-After` takes whole seconds; round up so the client never retries too early."""
    return {"Retry-After": str(max(math.ceil(seconds), 1))}


def client_ip(request: Request) -> str:
    """The caller's IP for per-IP limiting.

    WARNING: X-Forwarded-For is a plain header, so a client can send any value and get a fresh
    "IP" (and a fresh quota) on every request. The per-IP limit only stops honest or careless
    clients; the real protection of the LLM quota is the global limit (GLOBAL_RPM).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
