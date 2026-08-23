"""RQ job bodies. Each job opens its own checkpointer connection for the
duration of one graph run/resume -- simple and safe for a worker that may
process jobs across long gaps, at the cost of a per-job connection open
(acceptable at this system's volume).
"""
from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.core.logging import get_logger, log_error
from app.core.postgres import get_dsn
from app.graph.build import build_graph
from app.services import registry_service

logger = get_logger("tasks")


def _run(thread_id: str, invoke_arg) -> dict:
    with PostgresSaver.from_conn_string(get_dsn()) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer)
        return graph.invoke(invoke_arg, config={"configurable": {"thread_id": thread_id}})


def run_new_workflow(initial_state: dict) -> dict:
    workflow_id = initial_state["workflow_id"]
    try:
        return _run(workflow_id, initial_state)
    except Exception as e:
        log_error(logger, "workflow run failed", exc=e, workflow_id=workflow_id, operation="run_new_workflow")
        try:
            registry_service.update_workflow_run(workflow_id, status="failed")
        except Exception:
            pass
        raise


def run_resume(workflow_id: str, decision_payload: dict) -> dict:
    try:
        return _run(workflow_id, Command(resume=decision_payload))
    except Exception as e:
        log_error(logger, "workflow resume failed", exc=e, workflow_id=workflow_id, operation="run_resume")
        try:
            registry_service.update_workflow_run(workflow_id, status="failed")
        except Exception:
            pass
        raise
