from app.graph.build import (
    MAX_REGENERATIONS,
    _after_decision,
    _after_request_approval,
    _after_route,
    _after_score,
    _after_validate,
)


def test_after_score_routes_accepted_projects_forward():
    assert _after_score({"scores": {"action": "inserted"}}) == "route_action"
    assert _after_score({"scores": {"action": "replaced"}}) == "route_action"


def test_after_score_routes_rejected_projects_to_finalize():
    assert _after_score({"scores": {"action": "rejected"}}) == "finalize_workflow"
    assert _after_score({"scores": {"action": "ignored"}}) == "finalize_workflow"


def test_after_route_requires_selected_actions():
    assert _after_route({"selected_actions": ["resume"]}) == "generate_artifacts"
    assert _after_route({"selected_actions": []}) == "finalize_workflow"


def test_after_validate_requires_at_least_one_pass():
    assert _after_validate({"validation_results": {"resume": {"passed": True}}}) == "request_discord_approval"
    assert _after_validate({"validation_results": {"resume": {"passed": False}}}) == "finalize_workflow"


def test_after_request_approval_requires_pending_approvals():
    assert _after_request_approval({"approval_state": {"resume": {"status": "pending"}}}) == "await_approval"
    assert _after_request_approval({"approval_state": {}}) == "finalize_workflow"


def test_after_decision_waits_for_all_pending():
    state = {"approval_state": {"resume": {"status": "pending"}, "linkedin": {"status": "approved"}}}
    assert _after_decision(state) == "await_approval"


def test_after_decision_regenerates_on_changes_requested_within_retry_budget():
    state = {"approval_state": {"resume": {"status": "changes_requested"}}, "retry_count": 0}
    assert _after_decision(state) == "generate_artifacts"


def test_after_decision_stops_regenerating_past_retry_budget():
    state = {"approval_state": {"resume": {"status": "changes_requested"}}, "retry_count": MAX_REGENERATIONS}
    assert _after_decision(state) == "finalize_workflow"


def test_after_decision_publishes_on_approval():
    state = {"approval_state": {"resume": {"status": "approved"}}, "retry_count": 0}
    assert _after_decision(state) == "publish"


def test_after_decision_finalizes_on_full_rejection():
    state = {"approval_state": {"resume": {"status": "rejected"}}, "retry_count": 0}
    assert _after_decision(state) == "finalize_workflow"
