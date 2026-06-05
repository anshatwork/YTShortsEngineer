"""
agents/long_to_shorts/api/supabase_client.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Singleton Supabase client instances for the LongToShorts API.

Two clients are created at import time (lazily on first access):

  anon_client   — uses the SUPABASE_ANON_KEY; respects RLS; used only if needed
  worker_client — uses the SUPABASE_SERVICE_ROLE_KEY; bypasses RLS; used by
                  background runners (runner.py, edit_runner.py) where no user
                  session is available.

The URL and keys are read from environment variables so that the module is
import-safe even when the env is not yet configured (will raise at first use).
"""

from __future__ import annotations

import os
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_worker_client() -> Client:
    """Return the service-role Supabase client (bypasses RLS).

    Use only inside background threads / workers that have no user JWT.
    """
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Return the anon Supabase client (respects RLS)."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)


__all__ = ["get_worker_client", "get_anon_client"]
