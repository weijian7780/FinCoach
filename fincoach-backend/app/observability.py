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
            if "response" in locals():
                response.headers["X-Request-ID"] = request_id


def log_operation_trace(
    *,
    stage: str,
    request_id: str | None = None,
    part_id: str | None = None,
    variant: int | None = None,
    owner_programme: str | None = None,
    canonical_url: str | None = None,
    observed_status: str | None = None,
    extraction_method: str | None = None,
    content_size: int | None = None,
    content_hash: str | None = None,
    span_sizes: list[int] | None = None,
    terminal_reason: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    finish_reason: str | None = None,
    token_usage: dict[str, int | None] | None = None,
    elapsed_ms: float = 0.0,
    remaining_seconds: float | None = None,
    cache_state: str | None = None,
    billed_usage: int | float | None = None,
) -> dict:
    """Log an operation trace row with privacy-safe codes, hashes, and counts."""
    trace = {
        "event": "coach_operation_trace",
        "stage": stage,
        "request_id": request_id,
        "part_id": part_id,
        "variant": variant,
        "owner_programme": owner_programme,
        "canonical_url": canonical_url,
        "observed_status": observed_status,
        "extraction_method": extraction_method,
        "content_size": content_size,
        "content_hash": content_hash,
        "span_sizes": span_sizes,
        "terminal_reason": terminal_reason,
        "provider": provider,
        "model": model,
        "finish_reason": finish_reason,
        "token_usage": token_usage,
        "elapsed_ms": round(elapsed_ms, 1),
        "remaining_seconds": round(remaining_seconds, 2) if remaining_seconds is not None else None,
        "cache_state": cache_state,
        "billed_usage": billed_usage,
    }
    # Log to uvicorn.error where coach and research events are logged
    logging.getLogger("uvicorn.error").info(json.dumps(trace, separators=(",", ":")))
    return trace
