"""Simple in-memory per-client rate limiting middleware.

This is a development-friendly token-bucket limiter keyed by client IP (or
authenticated user id if available). For multi-process production
deployments, replace the in-memory store with Redis.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.limit = requests_per_minute
        self.window_seconds = 60
        self._hits: dict[str, deque] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        auth_user = getattr(request.state, "user_id", None)
        if auth_user:
            return f"user:{auth_user}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/health"}:
            return await call_next(request)

        key = self._client_key(request)
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()

        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down."}},
            )

        bucket.append(now)
        return await call_next(request)
