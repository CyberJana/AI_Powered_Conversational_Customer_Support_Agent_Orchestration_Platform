"""Structured request logging middleware."""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("aicsp.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request id, path, status, and latency for every request.

    Never logs request/response bodies (which may contain credentials or
    PII); only structural metadata.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = response.status_code if response else 500
            logger.info(
                "request_complete",
                extra={
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
            if response is not None:
                response.headers["X-Request-ID"] = request_id
