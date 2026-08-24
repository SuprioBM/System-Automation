"""Shared node decorator: every LangGraph node gets consistent logging,
timestamping, and error handling. Exceptions are always logged with full
context and re-raised (never swallowed) so LangGraph halts the run at the
last successfully checkpointed node rather than silently continuing broken.
"""
from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Callable

from langgraph.errors import GraphInterrupt

from app.core.errors import DevSyncError, ExternalServiceError, is_transient_error
from app.core.logging import get_logger, log_error, log_event
from app.core.redis_client import incr_attempt_counter, reset_attempt_counter
from app.services import registry_service

logger = get_logger("graph")


def node(name: str):
    def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        @functools.wraps(fn)
        def wrapped(state: dict) -> dict:
            workflow_id = state.get("workflow_id")
            log_event(logger, 20, f"node start: {name}", workflow_id=workflow_id,
                      run_id=state.get("run_id"), node=name, repository=state.get("repository"),
                      commit=state.get("commit"))
            attempt_key = f"devsync:node_attempts:{workflow_id}:{name}" if workflow_id else None
            try:
                result = fn(state) or {}
                timestamps = dict(state.get("timestamps") or {})
                timestamps[name] = datetime.now(timezone.utc).isoformat()
                result.setdefault("timestamps", timestamps)
                result.setdefault("current_node", name)
                if attempt_key:
                    reset_attempt_counter(attempt_key)  # this node succeeded -- forget prior attempts
                if workflow_id:
                    try:
                        registry_service.update_workflow_run(
                            workflow_id, current_node=name,
                            current_stage=result.get("current_stage", state.get("current_stage")),
                        )
                    except ExternalServiceError:
                        pass  # observability update failure must not abort the run
                log_event(logger, 20, f"node done: {name}", workflow_id=workflow_id, node=name)
                return result
            except GraphInterrupt:
                # LangGraph's own human-in-the-loop pause signal (raised by
                # interrupt()), not a failure -- re-raise immediately without
                # error logging or marking the workflow failed. LangGraph
                # itself handles this at the graph.invoke() level to pause
                # the run cleanly; the job that triggered it still succeeds.
                raise
            except Exception as e:
                service = getattr(e, "service", None) if isinstance(e, ExternalServiceError) else None
                operation = getattr(e, "operation", None) if isinstance(e, ExternalServiceError) else None
                status_code = getattr(e, "status_code", None) if isinstance(e, ExternalServiceError) else None
                error_type = "business_failure" if isinstance(e, DevSyncError) else "unexpected_exception"
                attempt_number = incr_attempt_counter(attempt_key) if attempt_key else 1
                transient = is_transient_error(e)

                # Every attempt is logged, whether or not LangGraph's
                # RetryPolicy will retry it automatically -- this node()
                # wrapper is re-invoked on each retry attempt (LangGraph
                # retries the whole registered action), so this naturally
                # captures every attempt, not just the final one.
                log_error(
                    logger, f"node failed (attempt {attempt_number}, {'transient' if transient else 'permanent'}): {name}",
                    exc=e, workflow_id=workflow_id, run_id=state.get("run_id"),
                    node=name, repository=state.get("repository"), commit=state.get("commit"),
                    service=service, operation=operation, status_code=status_code,
                    error_type=type(e).__name__, retry_number=attempt_number,
                )

                # Whether this specific attempt is the LAST one LangGraph will
                # make isn't knowable from inside the node (that's tracked
                # internally in langgraph.pregel.retry.run_with_retry, not
                # exposed here) -- so the DB is not marked "failed" here.
                # Only the outermost caller (tasks.py, wrapping the whole
                # graph.invoke()) knows the graph run has truly stopped with
                # no more automatic recovery pending; it reads these
                # attributes off the same exception object to build the
                # failure record and Discord notification.
                e.devsync_failed_node = name
                e.devsync_attempt_count = attempt_number
                e.devsync_transient = transient
                raise

        return wrapped

    return decorator
