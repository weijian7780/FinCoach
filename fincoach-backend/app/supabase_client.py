"""Single shared Supabase client (service-role)."""
from functools import lru_cache

from supabase import Client, create_client

from app.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL


@lru_cache
def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env "
            "(use the SERVICE ROLE key, not the publishable key)."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
