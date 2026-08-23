"""Worker entrypoint: python -m app.workers.worker

Uses rq.SimpleWorker (in-process, no os.fork) because this system targets
Windows dev environments as well as Linux containers, and RQ's default
forking Worker is POSIX-only. Restartable: on restart it just resumes
consuming the queue -- any workflow that crashed mid-run resumes from its
last LangGraph checkpoint the next time it (or a resume job) is invoked,
not from node 1.
"""
from __future__ import annotations

from rq import SimpleWorker

from app.core.config import REQUIRED_FOR_WORKER, validate_settings
from app.core.logging import get_logger
from app.core.redis_client import WORKFLOW_QUEUE_NAME, get_redis
from app.db.migrate import run as run_migrations

logger = get_logger("worker")


def main() -> None:
    validate_settings(REQUIRED_FOR_WORKER)
    run_migrations()
    logger.info("DevSync worker starting")
    worker = SimpleWorker([WORKFLOW_QUEUE_NAME], connection=get_redis())
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
