from __future__ import annotations

from app.core.redis_client import get_queue

JOB_TIMEOUT = 900  # seconds; a single node (e.g. LaTeX compile, LLM call) should never take this long


def enqueue_new_workflow(initial_state: dict):
    return get_queue().enqueue("app.workers.tasks.run_new_workflow", initial_state, job_timeout=JOB_TIMEOUT)


def enqueue_resume(workflow_id: str, decision_payload: dict):
    return get_queue().enqueue("app.workers.tasks.run_resume", workflow_id, decision_payload, job_timeout=JOB_TIMEOUT)


def enqueue_recovery(workflow_id: str):
    return get_queue().enqueue("app.workers.tasks.run_recovery", workflow_id, job_timeout=JOB_TIMEOUT)
