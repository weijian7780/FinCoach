"""Shared Supabase bearer-token verification for FastAPI routes."""

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.supabase_client import get_supabase


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    token: str


def require_authenticated_user(authorization: str | None) -> AuthenticatedUser:
    parts = authorization.split() if authorization else []
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    token = parts[1]
    try:
        response = get_supabase().auth.get_user(token)
        verified_user = getattr(response, "user", None)
        user_id = getattr(verified_user, "id", None)
        is_anonymous = bool(getattr(verified_user, "is_anonymous", False))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        ) from exc
    if not user_id or is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return AuthenticatedUser(user_id=str(user_id), token=token)
