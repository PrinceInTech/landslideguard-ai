"""Best-effort in-process rate limiting for authentication endpoints.

Scope and limitations
---------------------
This is a *local* safeguard, not distributed protection. Counters live in this
process's memory: they are reset on restart and are not shared across workers
or replicas, so they cannot enforce a global limit behind a load balancer.

Identity is the transport peer address (``request.client.host``). Forwarding
headers such as ``X-Forwarded-For`` are deliberately ignored because any client
can set them; trusting them would let an attacker bypass the limit by rotating
a header value. The trade-off is that behind a reverse proxy which does not
preserve the client address, every caller can share a single bucket. A
deployment that needs real protection must *additionally* rate-limit at the
proxy/gateway or add a shared store (e.g. Redis); this module never pretends to
provide that.

Storage is bounded so a hostile client cannot grow the table without limit, and
a rejected attempt fails *closed* with a generic ``429`` that reveals nothing
about whether an account exists.
"""
import os
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


def _positive_int_env(name: str, default: int) -> int:
    """Read a strictly-positive integer knob, falling back on anything odd."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass
class _Bucket:
    count: int
    reset_at: float


class FixedWindowLimiter:
    """A single-process fixed-window counter keyed by an opaque string.

    ``clock`` is injectable so tests can advance time deterministically without
    sleeping.
    """

    def __init__(self, limit, window_seconds, *, max_keys=4096, clock=time.monotonic):
        self.limit = limit
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    def hit(self, key: str) -> tuple[bool, int]:
        """Record one attempt for ``key``.

        Returns ``(allowed, retry_after_seconds)``. ``retry_after`` is 0 when the
        attempt is allowed and a positive whole number of seconds otherwise.
        """
        now = self._clock()
        with self._lock:
            self._evict(now)
            bucket = self._buckets.get(key)
            if bucket is None or bucket.reset_at <= now:
                self._buckets[key] = _Bucket(count=1, reset_at=now + self.window_seconds)
                return True, 0
            if bucket.count >= self.limit:
                return False, max(1, int(bucket.reset_at - now + 0.999))
            bucket.count += 1
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _evict(self, now: float) -> None:
        """Bound memory: drop expired buckets, then oldest-inserted if still full."""
        if len(self._buckets) < self._max_keys:
            return
        for key in [k for k, b in self._buckets.items() if b.reset_at <= now]:
            del self._buckets[key]
        while len(self._buckets) >= self._max_keys:
            self._buckets.pop(next(iter(self._buckets)))


_LIMITERS: list[FixedWindowLimiter] = []


def rate_limit(name: str, limit: int, window_seconds: int):
    """Build a FastAPI dependency enforcing ``limit`` per ``window_seconds``.

    The counter is keyed only by the client's transport address, so the same
    bucket is shared by all requests from one peer regardless of path.
    """
    limiter = FixedWindowLimiter(limit, window_seconds)
    _LIMITERS.append(limiter)

    def dependency(request: Request) -> None:
        allowed, retry_after = limiter.hit(_client_key(request))
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

    # Exposed for tests and diagnostics; not part of the public API surface.
    dependency.limiter = limiter
    dependency.limiter_name = name
    return dependency


def _client_key(request: Request) -> str:
    """Stable client identity from the transport peer only (never a header)."""
    client = request.client
    return client.host if client and client.host else "unknown"


def reset_rate_limits() -> None:
    """Clear every limiter's counters (used by the test suite)."""
    for limiter in _LIMITERS:
        limiter.reset()


# Conservative defaults; operators may override without code changes.
LOGIN_RATE_LIMIT = _positive_int_env("AUTH_LOGIN_RATE_LIMIT", 10)
LOGIN_RATE_WINDOW_SECONDS = _positive_int_env("AUTH_LOGIN_RATE_WINDOW_SECONDS", 60)
REGISTER_RATE_LIMIT = _positive_int_env("AUTH_REGISTER_RATE_LIMIT", 5)
REGISTER_RATE_WINDOW_SECONDS = _positive_int_env("AUTH_REGISTER_RATE_WINDOW_SECONDS", 300)

login_rate_limit = rate_limit("login", LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW_SECONDS)
register_rate_limit = rate_limit("register", REGISTER_RATE_LIMIT, REGISTER_RATE_WINDOW_SECONDS)
