from __future__ import annotations

from app.graph.util import node
from app.models.decisions import RouteDecision
from app.prompt.prompts import route_action_system, route_action_user
from app.services.groq_client import structured_call

ACCEPTED_ACTIONS = {"inserted", "replaced"}


@node("route_action")
def route_action(state: dict) -> dict:
    if state["scores"].get("action") not in ACCEPTED_ACTIONS:
        return {"current_stage": "routed", "selected_actions": []}

    decision: RouteDecision = structured_call(
        route_action_system(),
        route_action_user(state["project_data"], state["scores"]),
        RouteDecision,
        operation="route_action",
    )
    targets = [t for t in decision.targets if t != "none"]
    return {"current_stage": "routed", "selected_actions": targets}
