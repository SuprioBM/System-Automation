"""LangGraph topology assembly. One durable graph, checkpointed after every
node via a Postgres-backed checkpointer (Supabase's own database) so a
crashed worker resumes from the last completed node rather than restarting.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.analysis import analyze_repository, retrieve_relevant_knowledge, score_project, structure_project_knowledge
from app.graph.nodes.approval import MAX_REGENERATIONS, apply_approval_decision, await_approval, request_discord_approval
from app.graph.nodes.generation import generate_artifacts
from app.graph.nodes.intake import load_repository_context, receive_event
from app.graph.nodes.publish import finalize_workflow, publish
from app.graph.nodes.routing import route_action
from app.graph.nodes.validation import validate_artifacts
from app.models.state import WorkflowState


def _after_score(state: dict) -> str:
    return "route_action" if state.get("scores", {}).get("action") in ("inserted", "replaced") else "finalize_workflow"


def _after_route(state: dict) -> str:
    return "generate_artifacts" if state.get("selected_actions") else "finalize_workflow"


def _after_validate(state: dict) -> str:
    results = state.get("validation_results", {})
    return "request_discord_approval" if any(r.get("passed") for r in results.values()) else "finalize_workflow"


def _after_request_approval(state: dict) -> str:
    return "await_approval" if state.get("approval_state") else "finalize_workflow"


def _after_decision(state: dict) -> str:
    approval_state = state.get("approval_state", {})
    if any(v["status"] == "pending" for v in approval_state.values()):
        return "await_approval"
    if any(v["status"] == "changes_requested" for v in approval_state.values()) and state.get("retry_count", 0) < MAX_REGENERATIONS:
        return "generate_artifacts"
    if any(v["status"] == "approved" for v in approval_state.values()):
        return "publish"
    return "finalize_workflow"


def build_graph(checkpointer):
    builder = StateGraph(WorkflowState)

    for fn in (receive_event, load_repository_context, analyze_repository, structure_project_knowledge,
               retrieve_relevant_knowledge, score_project, route_action, generate_artifacts, validate_artifacts,
               request_discord_approval, await_approval, apply_approval_decision, publish, finalize_workflow):
        builder.add_node(fn.__name__, fn)

    builder.add_edge(START, "receive_event")
    builder.add_edge("receive_event", "load_repository_context")
    builder.add_edge("load_repository_context", "analyze_repository")
    builder.add_edge("analyze_repository", "structure_project_knowledge")
    builder.add_edge("structure_project_knowledge", "retrieve_relevant_knowledge")
    builder.add_edge("retrieve_relevant_knowledge", "score_project")
    builder.add_conditional_edges("score_project", _after_score, ["route_action", "finalize_workflow"])
    builder.add_conditional_edges("route_action", _after_route, ["generate_artifacts", "finalize_workflow"])
    builder.add_edge("generate_artifacts", "validate_artifacts")
    builder.add_conditional_edges("validate_artifacts", _after_validate, ["request_discord_approval", "finalize_workflow"])
    builder.add_conditional_edges("request_discord_approval", _after_request_approval, ["await_approval", "finalize_workflow"])
    builder.add_edge("await_approval", "apply_approval_decision")
    builder.add_conditional_edges(
        "apply_approval_decision", _after_decision,
        ["await_approval", "generate_artifacts", "publish", "finalize_workflow"],
    )
    builder.add_edge("publish", "finalize_workflow")
    builder.add_edge("finalize_workflow", END)

    return builder.compile(checkpointer=checkpointer)
