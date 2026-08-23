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

from app.core.errors import DevSyncError, ExternalServiceError
from app.core.logging import get_logger, log_error, log_event
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
            try:
                result = fn(state) or {}
                timestamps = dict(state.get("timestamps") or {})
                timestamps[name] = datetime.now(timezone.utc).isoformat()
                result.setdefault("timestamps", timestamps)
                result.setdefault("current_node", name)
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
                log_error(
                    logger, f"node failed: {name}", exc=e, workflow_id=workflow_id, run_id=state.get("run_id"),
                    node=name, repository=state.get("repository"), commit=state.get("commit"),
                    service=service, operation=operation, status_code=status_code, error_type=type(e).__name__,
                )
                if workflow_id:
                    try:
                        registry_service.update_workflow_run(
                            workflow_id, status="failed", current_node=name,
                            error_state={
                                "node": name, "service": service, "operation": operation,
                                "error_type": type(e).__name__, "message": str(e), "status_code": status_code,
                                "retry_number": state.get("retry_count", 0),
                            },
                        )
                    except ExternalServiceError:
                        pass
                raise

        return wrapped

    return decorator
