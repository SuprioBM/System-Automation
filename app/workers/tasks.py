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
from app.graph.build import build_graph
from app.services import registry_service

logger = get_logger("tasks")


def _run(thread_id: str, invoke_arg) -> dict:
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

        return graph.invoke(invoke_arg, config=config)


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
