"""Server-side admin authorization and narrowly scoped database operations."""
from fastapi import HTTPException
from app.auth import AuthenticatedUser
from app.supabase_client import get_supabase, retry_supabase_read


def admin_read(query):
    """Keep read failures actionable without returning fake or partial records."""
    try:
        return retry_supabase_read(query.execute)
    except Exception as exc:
        raise HTTPException(503, 'Administrative data is temporarily unavailable. Please retry.') from exc


def require_administrator(user: AuthenticatedUser) -> AuthenticatedUser:
    try:
        row = retry_supabase_read(get_supabase().table("account_access").select("role,status").eq("user_id", user.user_id).maybe_single().execute).data
    except Exception as exc:
        raise HTTPException(503, "Administrator permissions are unavailable.") from exc
    if not row or row.get("role") != "admin" or row.get("status") != "active":
        raise HTTPException(403, "Administrator access required.")
    return user


def admin_rpc(name: str, values: dict):
    try:
        return get_supabase().rpc(name, values).execute().data
    except Exception as exc:
        message = str(exc)
        if "ADMIN_CONFLICT" in message:
            raise HTTPException(409, "This record changed. Reload before continuing.") from exc
        if "ADMIN_INVALID" in message:
            raise HTTPException(422, "This action is not valid for the current record state.") from exc
        if "ADMIN_FORBIDDEN" in message:
            # The route already verified the administrator. Here it means the
            # target is protected or gone; a 403 would sign the panel out.
            raise HTTPException(409, "This record can no longer be changed here. Reload before continuing.") from exc
        raise HTTPException(503, "Administrative operation failed. Please retry.") from exc
