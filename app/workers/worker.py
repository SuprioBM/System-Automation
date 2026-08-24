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
from rq.timeouts import TimerDeathPenalty

from app.core.config import REQUIRED_FOR_WORKER, validate_settings
from app.core.logging import get_logger, log_error
from app.core.redis_client import WORKFLOW_QUEUE_NAME, acquire_claim, get_redis
from app.db.migrate import run as run_migrations

logger = get_logger("worker")


class PortableSimpleWorker(SimpleWorker):
    """SimpleWorker's default job-timeout enforcement (UnixSignalDeathPenalty)
    uses signal.SIGALRM, which doesn't exist on Windows and crashes every job
    with AttributeError. TimerDeathPenalty (threading-based) works on both."""
    death_penalty_class = TimerDeathPenalty


def _recover_orphaned_workflows() -> None:
    """Spec §12: a worker that gets killed mid-node (not a graceful failure
    -- nothing gets a chance to run except handlers or mark the workflow
    failed) leaves workflow_runs stuck at status='running' forever unless
    something notices. On every worker startup, find those and re-enqueue
    them for recovery from their last durable checkpoint -- no new GitHub
    commit required. The resume claim lock prevents this from double-firing
    against a workflow another worker is already legitimately processing."""
    from app.core.supabase import get_supabase
    from app.workers.queue import enqueue_recovery

    try:
        stuck = get_supabase().table("workflow_runs").select("workflow_id").eq("status", "running").execute().data or []
    except Exception as e:
        log_error(logger, "could not scan for orphaned workflows at startup", exc=e,
                  service="supabase", operation="recover_orphaned_workflows")
        return

    for row in stuck:
        workflow_id = row["workflow_id"]
        claim_key = f"devsync:resume_claim:{workflow_id}"
        if not acquire_claim(claim_key, ttl_seconds=120):
            continue  # another worker is already handling this one
        try:
            enqueue_recovery(workflow_id)
            logger.info(f"re-enqueued orphaned workflow for recovery: workflow_id={workflow_id}")
        except Exception as e:
            log_error(logger, "failed to re-enqueue orphaned workflow", exc=e, service="redis",
                      operation="enqueue_recovery", workflow_id=workflow_id)


def main() -> None:
    validate_settings(REQUIRED_FOR_WORKER)
    run_migrations()
    logger.info("DevSync worker starting")
    _recover_orphaned_workflows()
    worker = PortableSimpleWorker([WORKFLOW_QUEUE_NAME], connection=get_redis())
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
