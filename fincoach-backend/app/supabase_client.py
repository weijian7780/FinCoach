"""Single shared Supabase client (service-role)."""
from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.config import SUPABASE_PUBLISHABLE_KEY, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


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
