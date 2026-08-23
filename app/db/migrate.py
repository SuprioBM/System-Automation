"""Apply SQL migrations from app/db/migrations/*.sql against SUPABASE_DB_URL,
tracked in a schema_migrations table. Run with: python -m app.db.migrate
"""
from __future__ import annotations

import pathlib

from app.core.logging import get_logger, log_error
from app.core.postgres import connection

logger = get_logger("migrate")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def run() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists schema_migrations (
                    filename text primary key,
                    applied_at timestamptz not null default now()
                )
                """
            )
            conn.commit()
            cur.execute("select filename from schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

        for path in files:
            if path.name in applied:
                logger.info(f"skip already-applied {path.name}")
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
                conn.commit()
                logger.info(f"applied {path.name}")
            except Exception as e:
                conn.rollback()
                log_error(logger, f"migration failed: {path.name}", exc=e, operation="migrate", file=path.name)
                raise


if __name__ == "__main__":
    run()
