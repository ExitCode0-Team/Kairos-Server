"""
Thin wrapper around the Supabase Python client.

Uses the service role key so we can download any user's upload path when
the API validates the request (upload_id lookup or explicit user_id match).
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Create a single Supabase client per process."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)
