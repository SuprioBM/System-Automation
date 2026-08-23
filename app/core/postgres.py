"""Direct Postgres access against the Supabase database.

Used for (a) applying SQL migrations and (b) the LangGraph checkpointer,
which needs a raw connection string rather than the Supabase REST client.
Application-level CRUD (projects, artifacts, approvals) goes through
app.core.supabase (the REST client) instead -- this module is intentionally
narrow.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg

from app.core.config import require
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("postgres")


def get_dsn() -> str:
    return require("SUPABASE_DB_URL")


@contextmanager
def connection():
    try:
        conn = psycopg.connect(get_dsn())
    except psycopg.OperationalError as e:
        raise ExternalServiceError("supabase_postgres", "connect", str(e), original=e) from e
    try:
        yield conn
    finally:
        conn.close()
