"""Single shared Supabase client (service-role)."""
from functools import lru_cache
from typing import Callable, TypeVar

import httpx

from supabase import Client, ClientOptions, create_client

from app.config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


ReadResult = TypeVar('ReadResult')


def retry_supabase_read(operation: Callable[[], ReadResult]) -> ReadResult:
    """Retry a side-effect-free Auth GET or table SELECT once on transport failure.

    The SDK retries certain HTTP responses, but a disconnected connection raises
    before there is a response. Never use this helper for writes or mutating RPCs:
    a lost response cannot tell us whether a database change already committed.
    """
    try:
        return operation()
    except httpx.TransportError:
        return operation()


@lru_cache
def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env "
            "(use the SERVICE ROLE key, not the publishable key)."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def get_user_supabase(token: str) -> Client:
    """Create a request-scoped client whose queries remain subject to RLS."""
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY in .env.")
    if not token:
        raise ValueError("A verified Supabase access token is required.")
    options = ClientOptions(
        headers={"Authorization": f"Bearer {token}"},
        auto_refresh_token=False,
        persist_session=False,
    )
    return create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, options)
