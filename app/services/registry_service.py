"""Workflow-run registry, idempotency ledger, artifact versions, and
approvals. Kept as one module because these are thin, closely-related CRUD
operations over four small tables -- splitting them further would be
unnecessary abstraction for what they do.

Distinguishes three separate concerns per spec §24:
  - workflow_runs / processed_events: execution state & idempotency
  - artifacts / resume_versions: artifact version history
  - approvals: human-in-the-loop decisions, tied to an exact artifact version
    so a stale Discord interaction can never approve a newer/different one.

The LangGraph checkpoint tables (managed separately by
langgraph-checkpoint-postgres) are the actual durable graph state; the
`workflow_runs` row here is a queryable summary for the API/observability,
not the checkpoint mechanism itself.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import ExternalServiceError, StaleApprovalError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase

logger = get_logger("registry_service")


def _wrap(op: str, **ctx):
    def decorator(fn):
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                log_error(logger, f"{op} failed", exc=e, service="supabase", operation=op, **ctx)
                raise ExternalServiceError("supabase", op, str(e), original=e) from e
        return wrapped
    return decorator


# ── Idempotency ──────────────────────────────────────────────────────────

def is_duplicate_event(event_id: str) -> bool:
    res = get_supabase().table("processed_events").select("event_id").eq("event_id", event_id).execute()
    return bool(res.data)


def record_event(event_id: str, delivery_id: str | None, source: str, workflow_id: str | None = None) -> None:
    get_supabase().table("processed_events").upsert({
        "event_id": event_id, "delivery_id": delivery_id, "source": source, "workflow_id": workflow_id,
    }, on_conflict="event_id").execute()


# ── Workflow runs ────────────────────────────────────────────────────────

def create_workflow_run(workflow_id: str, run_id: str, event_id: str, repository: str, commit_sha: str) -> dict:
    existing = get_workflow_run(workflow_id)
    if existing:
        return existing
    res = get_supabase().table("workflow_runs").insert({
        "workflow_id": workflow_id, "run_id": run_id, "event_id": event_id,
        "repository": repository, "commit_sha": commit_sha, "status": "running",
    }).execute()
    return res.data[0]


def get_workflow_run(workflow_id: str) -> dict | None:
    res = get_supabase().table("workflow_runs").select("*").eq("workflow_id", workflow_id).execute()
    return res.data[0] if res.data else None


def update_workflow_run(workflow_id: str, **fields) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    get_supabase().table("workflow_runs").update(fields).eq("workflow_id", workflow_id).execute()


# ── Artifacts ────────────────────────────────────────────────────────────

def create_artifact(workflow_id: str, run_id: str, artifact_type: str, content: dict,
                     validation_results: dict | None = None) -> dict:
    existing = get_supabase().table("artifacts").select("version") \
        .eq("workflow_id", workflow_id).eq("artifact_type", artifact_type) \
        .order("version", desc=True).limit(1).execute()
    next_version = (existing.data[0]["version"] + 1) if existing.data else 1
    res = get_supabase().table("artifacts").insert({
        "workflow_id": workflow_id, "run_id": run_id, "artifact_type": artifact_type,
        "version": next_version, "status": "draft", "content": content,
        "validation_results": validation_results,
    }).execute()
    return res.data[0]


def get_artifact(artifact_id: str) -> dict | None:
    res = get_supabase().table("artifacts").select("*").eq("id", artifact_id).execute()
    return res.data[0] if res.data else None


def get_latest_artifact(workflow_id: str, artifact_type: str) -> dict | None:
    res = get_supabase().table("artifacts").select("*") \
        .eq("workflow_id", workflow_id).eq("artifact_type", artifact_type) \
        .order("version", desc=True).limit(1).execute()
    return res.data[0] if res.data else None


def set_artifact_status(artifact_id: str, status: str, approved_at: str | None = None) -> None:
    fields = {"status": status}
    if approved_at:
        fields["approved_at"] = approved_at
    get_supabase().table("artifacts").update(fields).eq("id", artifact_id).execute()


# ── Approvals ────────────────────────────────────────────────────────────

def create_approval_request(workflow_id: str, run_id: str, artifact_id: str, artifact_version: int,
                             channel: str = "discord") -> dict:
    res = get_supabase().table("approvals").insert({
        "workflow_id": workflow_id, "run_id": run_id, "artifact_id": artifact_id,
        "artifact_version": artifact_version, "channel": channel, "status": "pending",
    }).execute()
    return res.data[0]


def set_discord_message_id(approval_id: str, message_id: str) -> None:
    get_supabase().table("approvals").update({"discord_message_id": message_id}).eq("id", approval_id).execute()


def get_approval(approval_id: str) -> dict | None:
    res = get_supabase().table("approvals").select("*").eq("id", approval_id).execute()
    return res.data[0] if res.data else None


def decide_approval(approval_id: str, status: str, feedback: str | None = None) -> dict:
    """Apply a human decision, after verifying the approval still targets the
    current version of its artifact -- a stale interaction (an old Discord
    message for a superseded draft) is rejected rather than silently applied."""
    approval = get_approval(approval_id)
    if not approval:
        raise ExternalServiceError("supabase", "decide_approval", f"approval {approval_id} not found")

    artifact = get_artifact(approval["artifact_id"])
    if not artifact or artifact["version"] != approval["artifact_version"] or artifact["status"] != "draft":
        raise StaleApprovalError(
            f"approval {approval_id} targets artifact version {approval['artifact_version']} "
            f"but the artifact is now at version {artifact['version'] if artifact else 'missing'} "
            f"(status={artifact['status'] if artifact else 'n/a'})"
        )

    get_supabase().table("approvals").update({
        "status": status, "feedback": feedback, "decided_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", approval_id).execute()
    return get_approval(approval_id)
