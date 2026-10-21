"""Allowlisted completion telemetry; never log prompts or provider reasoning."""
from __future__ import annotations


def _value(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _count(obj, name):
    value = _value(obj, name)
    return value if type(value) is int and value >= 0 else None


def completion_metadata(response: object, *, max_tokens: int, timeout_seconds: float) -> dict:
    choices = _value(response, 'choices', ()) or ()
    reason = _value(choices[0], 'finish_reason') if choices else None
    # Native Gemini metadata is useful when exposed by a compatible endpoint.
    reason = reason or _value(response, 'finish_reason')
    usage = _value(response, 'usage') or _value(response, 'usage_metadata') or _value(response, 'usageMetadata')
    prompt = _count(usage, 'prompt_tokens')
    completion = _count(usage, 'completion_tokens')
    total = _count(usage, 'total_tokens')
    native = prompt is None and completion is None
    if native:
        prompt = _count(usage, 'promptTokenCount')
        completion = _count(usage, 'candidatesTokenCount')
        total = _count(usage, 'totalTokenCount')
    reasoning = _count(_value(usage, 'completion_tokens_details'), 'reasoning_tokens')
    if reasoning is None:
        reasoning = _count(usage, 'thoughtsTokenCount')
    residual = total - prompt - completion if None not in (total, prompt, completion) else None
    return dict(finish_reason=reason if isinstance(reason, str) else None,
        requested_max_tokens=max_tokens, applied_timeout_seconds=round(timeout_seconds, 3),
        prompt_tokens=prompt, completion_tokens=completion, reasoning_tokens=reasoning,
        total_tokens=total, accounting_residual_tokens=residual,
        truncated=str(reason).upper() in {'LENGTH', 'MAX_TOKENS'},
        # Native candidate usage may exclude thinking; do not compare it to a combined cap.
        near_cap=not native and completion is not None and completion >= max_tokens * .95)


RESULT_METADATA_FIELDS = ('finish_reason', 'requested_max_tokens', 'reasoning_tokens',
                          'total_tokens', 'applied_timeout_seconds')


def result_metadata(result) -> dict:
    return {name: getattr(result, name, None) for name in RESULT_METADATA_FIELDS}


def provider_error_code(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or 'timeout' in name:
        return 'verifier_timeout'
    if getattr(exc, 'status_code', None) is not None or any(word in name for word in ('http', 'ratelimit', 'connection', 'apierror')):
        return 'verifier_http_error'
    return 'verifier_unavailable'
