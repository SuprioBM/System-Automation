"""Typed LangGraph workflow state.

A TypedDict (LangGraph's native state schema type) with explicit, named
fields rather than one unstructured dict. Nested values are kept as plain
JSON-serializable dict/list/str/... (not live Pydantic instances) so the
Postgres checkpointer can serialize the state after every node without
pickling concerns -- Pydantic models in app.models.* are used at each node's
boundary to validate/build these dicts, via .model_dump()/.model_validate().
"""
from __future__ import annotations

from typing import Any, Literal

# LangGraph builds pydantic schemas from this TypedDict for validation/graph
# introspection; on Python < 3.12, typing.TypedDict doesn't carry the runtime
# metadata pydantic needs for that, so typing_extensions.TypedDict is required
# here regardless of interpreter version.
from typing_extensions import TypedDict

Stage = Literal[
    "received",
    "context_loaded",
    "analyzed",
    "structured",
    "retrieved",
    "scored",
    "routed",
    "generated",
    "validated",
    "awaiting_approval",
    "published",
    "rejected",
    "failed",
]


class ErrorState(TypedDict, total=False):
    node: str
    service: str | None
    operation: str | None
    error_type: str
    message: str
    status_code: int | None
    retry_number: int


class WorkflowState(TypedDict, total=False):
    # Identity / observability
    workflow_id: str
    run_id: str
    event_id: str
    repository: str
    commit: str
    commit_message: str
    user: str
    installation_id: int | None

    # Progress
    current_stage: Stage
    current_node: str
    retry_count: int
    timestamps: dict[str, str]

    # Domain data, populated as the graph progresses
    raw_event: dict[str, Any]
    project_data: dict[str, Any]  # RepoAnalysis.model_dump() merged with repo metadata
    retrieved_context: list[dict[str, Any]]  # RAG hits: [{content, score, metadata}]
    candidate_projects: list[dict[str, Any]]  # existing projects considered for scoring
    scores: dict[str, Any]  # ScoringDecision.model_dump()
    selected_actions: list[str]  # RouteDecision.targets

    # Artifact generation
    generated_outputs: dict[str, Any]  # {resume: {...}, linkedin: {...}, portfolio: {...}}
    artifacts: dict[str, Any]  # {resume: artifact_id, linkedin_post: artifact_id, ...} + versions
    validation_results: dict[str, Any]

    # Human-in-the-loop
    approval_state: dict[str, Any]  # {resume: "pending"/"approved"/..., ...}
    approval_feedback: dict[str, Any]
    resume_state: dict[str, Any]  # slot-modification specific progress
    linkedin_state: dict[str, Any]  # image/post generation progress

    # Failure handling
    error_state: ErrorState | None

    project_slug: str | None
