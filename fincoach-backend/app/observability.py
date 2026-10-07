"""Privacy-safe HTTP request correlation and structured logging."""

import json
import logging
from time import monotonic
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


LOGGER = logging.getLogger("fincoach.http")


def _request_id(value: str | None) -> str:
    """Accept a canonical UUID only; reject arbitrary or oversized header data."""
    if value and len(value) <= 36:
        try:
            parsed = UUID(value)
            if str(parsed) == value.lower():
                return str(parsed)
        except ValueError:
            pass
    return str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started = monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed_ms = round((monotonic() - started) * 1000, 2)
            event = {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "route": request.url.path,
                "status": status_code,
                "elapsed_ms": elapsed_ms,
            }
            LOGGER.info(json.dumps(event, separators=(",", ":")))
            if "response" in locals():
                response.headers["X-Request-ID"] = request_id
