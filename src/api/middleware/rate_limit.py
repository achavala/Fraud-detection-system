import time
from collections import defaultdict
from typing import Callable

from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.config import get_settings

settings = get_settings()

DEFAULT_RPS = 1000
BUCKET_TTL_SECONDS = 60

PER_USER_RPS: dict[str, int] = {
    "admin": 10000,
    "model_risk": 5000,
    "investigator": 2000,
    "readonly": 500,
}


def _cleanup_expired_buckets(store: dict[str, list[float]], now: float) -> None:
    cutoff = now - BUCKET_TTL_SECONDS
    keys_to_delete = [k for k, timestamps in store.items() if timestamps and timestamps[-1] < cutoff]
    for k in keys_to_delete:
        del store[k]


class RateLimitStore:
    """In-memory sliding-window rate limit store."""

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


_ip_store = RateLimitStore()
_user_store = RateLimitStore()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_jwt_identity(request: Request) -> tuple[str | None, str | None]:
    """Extract user_id and role from a Bearer token without raising."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, None
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("user_id"), payload.get("role")
    except JWTError:
        return None, None


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
    """Two-tier rate limiting: per-IP global + per-JWT-user limits."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        client_ip = _get_client_ip(request)
        path = request.url.path
        path_prefix = _get_path_prefix(path)
        now = time.monotonic()

        # Tier 1: per-IP rate limit (global)
        ip_limit = _get_limit_for_path(path)
        ip_allowed, ip_limit_val, ip_remaining = _ip_store.check_and_increment(
            client_ip, path_prefix, ip_limit, now
        )

        # Tier 2: per-user rate limit (if JWT present)
        user_id, role = _extract_jwt_identity(request)
        user_allowed = True
        user_limit_val = 0
        user_remaining = 0

        if user_id:
            user_rps = PER_USER_RPS.get(role or "", DEFAULT_RPS)
            user_allowed, user_limit_val, user_remaining = _user_store.check_and_increment(
                user_id, path_prefix, user_rps, now
            )

        reset_ts = int(time.time()) + 1
        effective_limit = min(ip_limit_val, user_limit_val) if user_id else ip_limit_val
        effective_remaining = min(ip_remaining, user_remaining) if user_id else ip_remaining

        rate_limit_headers = {
            "X-RateLimit-Limit": str(effective_limit),
            "X-RateLimit-Remaining": str(effective_remaining),
            "X-RateLimit-Reset": str(reset_ts),
        }

        if not ip_allowed or not user_allowed:
            scope = "user" if not user_allowed else "ip"
            rate_limit_headers["X-RateLimit-Scope"] = scope
            return Response(
                content=f'{{"detail":"Too Many Requests","scope":"{scope}"}}',
                status_code=429,
                media_type="application/json",
                headers=rate_limit_headers,
            )

        response = await call_next(request)
        for k, v in rate_limit_headers.items():
            response.headers[k] = v
        return response
