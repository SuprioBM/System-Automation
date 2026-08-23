from __future__ import annotations

from datetime import datetime, timezone

import requests
from langgraph.types import interrupt

from app.core.config import settings
from app.graph.util import node
from app.services import discord_service, registry_service

MAX_REGENERATIONS = 3


def _channel_for(artifact_type: str) -> int:
    if artifact_type == "linkedin":
        return settings.discord_linkedin_channel_id
    return settings.discord_resume_channel_id  # resume + portfolio share the resume review channel


def _summary(artifact_type: str, content: dict) -> str:
    if artifact_type == "resume":
        return "New résumé slot content: " + "; ".join(content.get("bullets", [])[:2])
    if artifact_type == "linkedin":
        return content.get("post", "")[:300]
    if artifact_type == "portfolio":
        p = content.get("project", {})
        return f"{content.get('action')} '{p.get('name')}' in {p.get('category')}" + (
            f" (replacing '{content.get('removed')}')" if content.get("removed") else ""
        )
    return ""


def _validation_summary(result: dict) -> str:
    if not result:
        return "n/a"
    checks = {**result.get("technical_checks", {}), **result.get("content_checks", {}), **result.get("quality_checks", {})}
    parts = [f"{k}={'ok' if v else 'FAIL'}" for k, v in checks.items()]
    return ", ".join(parts) if parts else ("passed" if result.get("passed") else "failed")


@node("request_discord_approval")
def request_discord_approval(state: dict) -> dict:
    outputs = state.get("generated_outputs", {})
    validation = state.get("validation_results", {})
    workflow_id, run_id = state["workflow_id"], state["run_id"]
    approval_state: dict = {}

    for artifact_type, content in outputs.items():
        result = validation.get(artifact_type, {})
        if not result.get("passed"):
            continue

        artifact = registry_service.create_artifact(workflow_id, run_id, artifact_type, content, result)
        approval = registry_service.create_approval_request(workflow_id, run_id, artifact["id"], artifact["version"])

        link = content.get("pdf_draft_url") or content.get("image_url")
        message = discord_service.build_approval_content(
            workflow_id=workflow_id, artifact_type=artifact_type,
            what_changed=_summary(artifact_type, content), why=state.get("scores", {}).get("reasoning", ""),
            validation_summary=_validation_summary(result), link=link,
        )

        file_bytes, filename = None, None
        if artifact_type == "resume" and content.get("pdf_draft_url"):
            try:
                res = requests.get(content["pdf_draft_url"], timeout=30)
                if res.status_code == 200:
                    file_bytes, filename = res.content, "resume-draft.pdf"
            except requests.RequestException:
                pass  # the message still links to the draft URL if attaching the file fails

        message_id = discord_service.send_approval_message(
            _channel_for(artifact_type), message, approval["id"], file_bytes, filename
        )
        registry_service.set_discord_message_id(approval["id"], message_id)
        approval_state[artifact_type] = {"approval_id": approval["id"], "artifact_id": artifact["id"], "status": "pending"}

    return {
        "current_stage": "awaiting_approval",
        "approval_state": approval_state,
        "artifacts": {k: v["artifact_id"] for k, v in approval_state.items()},
    }


@node("await_approval")
def await_approval(state: dict) -> dict:
    pending = [k for k, v in state.get("approval_state", {}).items() if v["status"] == "pending"]
    if state.get("workflow_id"):
        # Recorded before interrupt() raises, since it never returns normally
        # here -- the workflow is durably paused, not failed.
        registry_service.update_workflow_run(state["workflow_id"], status="awaiting_approval")
    decision = interrupt({"workflow_id": state["workflow_id"], "pending": pending})
    feedback_state = dict(state.get("approval_feedback") or {})
    feedback_state["_incoming"] = decision
    return {"approval_feedback": feedback_state}


@node("apply_approval_decision")
def apply_approval_decision(state: dict) -> dict:
    incoming = (state.get("approval_feedback") or {}).get("_incoming") or {}
    approval_state = dict(state.get("approval_state", {}))
    approval_id, status, feedback = incoming.get("approval_id"), incoming.get("status"), incoming.get("feedback")

    for artifact_type, info in list(approval_state.items()):
        if info.get("approval_id") == approval_id:
            approval_state[artifact_type] = {**info, "status": status, "feedback": feedback}
            new_status = {"approved": "approved", "rejected": "rejected"}.get(status, "draft")
            registry_service.set_artifact_status(
                info["artifact_id"], new_status,
                approved_at=datetime.now(timezone.utc).isoformat() if status == "approved" else None,
            )

    feedback_state = dict(state.get("approval_feedback") or {})
    feedback_state.pop("_incoming", None)
    retry_count = state.get("retry_count", 0)
    if status == "changes_requested" and feedback:
        feedback_state["_last_feedback"] = feedback
        retry_count += 1

    return {"approval_state": approval_state, "approval_feedback": feedback_state, "retry_count": retry_count}
