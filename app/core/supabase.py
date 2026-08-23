"""Shared Supabase REST client for application-level CRUD (projects,
artifacts, approvals, workflow_runs, processed_events). Always uses the
service-role key -- this module is backend-only and must never be imported
from anything served to a browser. Direct Postgres access (migrations,
LangGraph checkpointing) goes through app.core.postgres instead.
"""
from __future__ import annotations

from supabase import Client, create_client

from app.core.config import require, settings
from app.core.errors import ExternalServiceError

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = require("SUPABASE_URL")
        key = require("SUPABASE_SERVICE_ROLE_KEY")
        try:
            _client = create_client(url, key)
        except Exception as e:
            raise ExternalServiceError("supabase", "create_client", str(e), original=e) from e
    return _client


# Backwards-compatible module-level accessor used by existing call sites.
class _LazyClient:
    def __getattr__(self, item):
        return getattr(get_supabase(), item)


supabase = _LazyClient()
