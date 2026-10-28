"""Shared Supabase bearer-token verification for FastAPI routes."""

from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.supabase_client import get_supabase, retry_supabase_read


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    token: str


def _is_auth_service_failure(exc: Exception) -> bool:
    from supabase_auth.errors import AuthApiError, AuthRetryableError
    if isinstance(exc, AuthRetryableError):
        return True
    status_code = getattr(exc, "status", None)
    return isinstance(exc, AuthApiError) and isinstance(status_code, int) and (status_code == 429 or status_code >= 500)


def require_authenticated_user(authorization: str | None) -> AuthenticatedUser:
    parts = authorization.split() if authorization else []
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    token = parts[1]
    try:
        response = retry_supabase_read(lambda: get_supabase().auth.get_user(token))
        verified_user = getattr(response, "user", None)
        user_id = getattr(verified_user, "id", None)
        is_anonymous = bool(getattr(verified_user, "is_anonymous", False))
    except httpx.TransportError as exc:
        # A network outage must not be reported as invalid credentials.
        raise HTTPException(503, 'Authentication verification is temporarily unavailable.') from exc
    except Exception as exc:
        # Supabase Auth outages and rate limits arrive as SDK errors, not
        # transport errors. Reporting them as 401 makes clients sign out.
        if _is_auth_service_failure(exc):
            raise HTTPException(503, 'Authentication verification is temporarily unavailable.') from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc
    if not user_id or is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    from app.config import ACCOUNT_ACCESS_ENFORCED
    if ACCOUNT_ACCESS_ENFORCED:
        try:
            row = retry_supabase_read(get_supabase().table("account_access").select("status").eq("user_id", str(user_id)).maybe_single().execute).data
        except Exception as exc:
            raise HTTPException(503, "Account access verification is unavailable.") from exc
        if not row or row.get("status") != "active":
            raise HTTPException(403, "Account access is suspended.")
    return AuthenticatedUser(user_id=str(user_id), token=token)
