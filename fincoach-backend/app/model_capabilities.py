"""Request options decided by each model's published capabilities, not by its name.

OpenRouter publishes, for every model, the request parameters it accepts. With
``provider.require_parameters=true`` a request carrying a parameter the model does
not list has no eligible endpoint and fails (HTTP 404 "no endpoints"). This module
reads that published list once, caches it, and lets callers drop what a model does
not accept and choose the strongest structured-output form it supports.

When the list is unavailable (other hosts, no network, an error) nothing changes:
callers keep today's request shape.
"""
from __future__ import annotations

import json
import logging
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

from app.config import (COACH_MODEL_LISTING_RETRY_SECONDS, COACH_MODEL_LISTING_TIMEOUT_SECONDS,
                        COACH_MODEL_LISTING_TTL_SECONDS)

logger = logging.getLogger("uvicorn.error")

# Keys that belong to the SDK call itself rather than to the model's sampling
# parameters. They are part of the OpenAI client protocol, not a model rule.
_CALL_KEYS = frozenset({"model", "messages", "stream", "extra_body", "extra_headers",
                        "extra_query", "timeout"})

_lock = Lock()
_cache: dict[str, tuple[float, dict[str, frozenset[str]] | None]] = {}


def _listing_url(base_url: str) -> str | None:
    """Only OpenRouter publishes per-model supported parameters at /models."""
    parsed = urlparse(base_url or "")
    if parsed.hostname != "openrouter.ai":
        return None
    return base_url.rstrip("/") + "/models"


def _fetch(url: str) -> dict[str, frozenset[str]]:
    import httpx

    response = httpx.get(url, timeout=COACH_MODEL_LISTING_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json().get("data") or []
    return {str(item["id"]): frozenset(map(str, item.get("supported_parameters") or ()))
            for item in data if isinstance(item, dict) and item.get("id")}


def supported_parameters(base_url: str, model: str) -> frozenset[str] | None:
    """The model's published parameters, or None when they cannot be known."""
    url = _listing_url(base_url)
    if url is None:
        return None
    now = monotonic()
    with _lock:
        cached = _cache.get(url)
        fresh = cached and now < cached[0]
    if not fresh:
        try:
            listing = _fetch(url)
            expires = now + COACH_MODEL_LISTING_TTL_SECONDS
        except Exception as error:
            listing = None
            expires = now + COACH_MODEL_LISTING_RETRY_SECONDS
            logger.info(json.dumps({"event": "coach_model_listing_unavailable",
                                    "error_type": type(error).__name__}))
        with _lock:
            _cache[url] = (expires, listing)
            cached = _cache[url]
    listing = cached[1]
    if listing is None:
        return None
    return listing.get(model)


def fit_request(base_url: str, request: dict) -> dict:
    """Drop every model parameter the model does not publish; keep call keys."""
    supported = supported_parameters(base_url, str(request.get("model") or ""))
    if supported is None:
        return request
    dropped = sorted(key for key in request if key not in _CALL_KEYS and key not in supported)
    if not dropped:
        return request
    logger.info(json.dumps({"event": "coach_request_parameters_omitted",
                            "model": request.get("model"), "parameters": dropped}))
    return {key: value for key, value in request.items() if key not in dropped}


def structured_response_format(base_url: str, model: str, schema: dict, name: str) -> dict | None:
    """The strongest structured-output form the model publishes, if any."""
    supported = supported_parameters(base_url, model)
    if not supported:
        return None
    if "structured_outputs" in supported and "response_format" in supported:
        return {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
    if "response_format" in supported:
        return {"type": "json_object"}
    return None


def clear_cache() -> None:
    """Tests only."""
    with _lock:
        _cache.clear()
