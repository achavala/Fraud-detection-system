from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import get_settings

settings = get_settings()

DEFAULT_RPS = 1000
BUCKET_TTL_SECONDS = 60


def _cleanup_expired_buckets(store: dict[str, list[float]], now: float) -> None:
    """Remove buckets older than BUCKET_TTL_SECONDS."""
    cutoff = now - BUCKET_TTL_SECONDS
    keys_to_delete = [k for k, timestamps in store.items() if timestamps and timestamps[-1] < cutoff]
    for k in keys_to_delete:
        del store[k]


class RateLimitStore:
    """In-memory rate limit store with TTL cleanup. Sliding window per-second buckets."""

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = defaultdict(list)

    def _key(self, client_id: str, path_prefix: str) -> str:
        return f"{client_id}:{path_prefix}"

    def check_and_increment(
        self,
        client_id: str,
        path_prefix: str,
        limit_rps: int,
        now: float,
    ) -> tuple[bool, int, int]:
        """
        Sliding window: count requests in the last 1 second, allow if under limit.
        Returns (allowed, limit, remaining).
        """
        _cleanup_expired_buckets(self._store, now)
        key = self._key(client_id, path_prefix)
        window_start = now - 1.0
        self._store[key] = [t for t in self._store[key] if t > window_start]
        count = len(self._store[key])
        allowed = count < limit_rps
        if allowed:
            self._store[key].append(now)
            count += 1
        remaining = max(0, limit_rps - count)
        return allowed, limit_rps, remaining


_store = RateLimitStore()


def _get_client_id(request: Request) -> str:
    """Identify client by X-Forwarded-For or client host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_limit_for_path(path: str) -> int:
    if path.startswith("/authorize/"):
        return settings.rate_limit_scoring_rps
    if path.startswith("/dashboard/"):
        return settings.rate_limit_dashboard_rps
    return DEFAULT_RPS


def _get_path_prefix(path: str) -> str:
    if path.startswith("/authorize/"):
        return "authorize"
    if path.startswith("/dashboard/"):
        return "dashboard"
    return "default"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with per-path limits and sliding window algorithm."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        client_id = _get_client_id(request)
        path = request.url.path
        limit_rps = _get_limit_for_path(path)
        path_prefix = _get_path_prefix(path)
        now = time.monotonic()

        allowed, limit, remaining = _store.check_and_increment(
            client_id, path_prefix, limit_rps, now
        )

        reset_ts = int(time.time()) + 1
        rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_ts),
        }

        if not allowed:
            return Response(
                content='{"detail":"Too Many Requests"}',
                status_code=429,
                media_type="application/json",
                headers=rate_limit_headers,
            )

        response = await call_next(request)
        for k, v in rate_limit_headers.items():
            response.headers[k] = v
        return response
