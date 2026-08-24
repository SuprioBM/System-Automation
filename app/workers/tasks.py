"""RQ job bodies. Each job opens its own checkpointer connection for the
duration of one graph run/resume -- simple and safe for a worker that may
process jobs across long gaps, at the cost of a per-job connection open
(acceptable at this system's volume).
"""
from __future__ import annotations

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row

from app.core.logging import get_logger, log_error
from app.core.postgres import get_dsn
from app.core.errors import IdempotencyConflict
from app.core.redis_client import acquire_claim, release_claim
from app.graph.build import build_graph
from app.services import failure_recovery_service, registry_service
from app.workers.queue import JOB_TIMEOUT

logger = get_logger("tasks")


def _run(thread_id: str, invoke_arg) -> dict:
    # A separate lock from the Discord-click "resume_claim" (which only
    # guards against a duplicate Resume *click* before enqueueing): this one
    # wraps every actual execution of this thread_id, regardless of entry
    # point (new/resume/recovery), so a worker-restart orphan-recovery scan
    # can never race a still-genuinely-running execution of the same
    # workflow into double-invoking the graph concurrently (spec §9/§12).
    executing_key = f"devsync:executing:{thread_id}"
    if not acquire_claim(executing_key, ttl_seconds=JOB_TIMEOUT):
        raise IdempotencyConflict(f"workflow {thread_id} is already executing elsewhere")
    try:
        return _run_locked(thread_id, invoke_arg)
    finally:
        release_claim(executing_key)


def _run_locked(thread_id: str, invoke_arg) -> dict:
    # Not using PostgresSaver.from_conn_string(): it hard-codes
    # prepare_threshold=0 (prepare aggressively), which breaks under
    # Supabase's PgBouncer transaction-pooler connection multiplexing
    # (DuplicatePreparedStatement / prepared statement not found errors,
    # since a statement prepared on one pooled backend connection isn't
    # available on the next). prepare_threshold=None disables server-side
    # prepared statements entirely, which works with any pooler mode.
    with psycopg.connect(get_dsn(), autocommit=True, prepare_threshold=None, row_factory=dict_row) as conn:
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # If a checkpoint already exists for this workflow_id, a prior attempt
        # got at least one node in before crashing/failing. Resuming with the
        # full initial_state as `input` would make LangGraph start a fresh run
        # from START, re-doing every already-completed node (re-fetching
        # GitHub, re-calling Groq, re-indexing pgvector...). Passing None
        # instead tells LangGraph to continue the existing run from its last
        # checkpoint -- this is the actual "resume from node N, not node 1"
        # recovery behavior, not just a retry that happens to look similar.
        if not isinstance(invoke_arg, Command) and checkpointer.get_tuple(config) is not None:
            invoke_arg = None

        try:
            result = graph.invoke(invoke_arg, config=config)
        except Exception as e:
            # All of LangGraph's own per-node RetryPolicy attempts are
            # exhausted (or the error was permanent to begin with) -- this is
            # the one place that reliably knows the run has truly stopped
            # with no more automatic recovery pending. The checkpoint itself
            # is untouched; only workflow_runs + the Discord notification.
            tup = checkpointer.get_tuple(config)
            checkpoint_state = tup.checkpoint["channel_values"] if tup else {}
            failed_node = getattr(e, "devsync_failed_node", None) or checkpoint_state.get("current_node") or "unknown"
            attempts = getattr(e, "devsync_attempt_count", None) or 1
            log_error(logger, "workflow run stopped -- no more automatic recovery pending", exc=e,
                      workflow_id=thread_id, node=failed_node, retry_number=attempts,
                      error_type=type(e).__name__)
            try:
                registry_service.mark_workflow_failed(
                    thread_id, failed_node=failed_node, error=e, attempt_count=attempts,
                )
            except Exception:
                pass  # never let observability/notification failures mask the original error
            failure_recovery_service.notify_failure(thread_id, e, checkpoint_state)
            raise
        else:
            # A successful invoke may still land on "awaiting_approval" or
            # "completed" -- either way it's no longer in a failed state, so
            # any previous failure notification for this workflow should
            # reflect that rather than still showing the old failure.
            try:
                run = registry_service.get_workflow_run(thread_id)
                if run and run.get("status") == "completed":
                    failure_recovery_service.notify_recovered(thread_id)
            except Exception:
                pass
            return result


def run_new_workflow(initial_state: dict) -> dict:
    workflow_id = initial_state["workflow_id"]
    return _run(workflow_id, initial_state)


def run_resume(workflow_id: str, decision_payload: dict) -> dict:
    return _run(workflow_id, Command(resume=decision_payload))


def run_recovery(workflow_id: str) -> dict:
    """Discord Resume (or worker-restart auto-recovery) on a FAILED,
    recoverable workflow -- same workflow_id, continues from its latest
    checkpoint via the None-invoke_arg branch in _run(). Releases the
    resume claim once this attempt is truly done (success or exhausted
    failure) so a later, legitimate resume isn't blocked by a stale claim."""
    claim_key = f"devsync:resume_claim:{workflow_id}"
    try:
        return _run(workflow_id, None)
    finally:
        release_claim(claim_key)
