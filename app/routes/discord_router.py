"""Receives approve/reject/request-changes decisions from the Discord bot
process and resumes the corresponding LangGraph run. Requires the shared
secret the bot sends (DISCORD_CALLBACK_SHARED_SECRET) -- this is not a
public endpoint. Rejects (409) any decision on a stale/superseded artifact
version rather than silently applying it.
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import require
from app.core.errors import StaleApprovalError
from app.core.logging import get_logger, log_error
from app.core.redis_client import acquire_claim
from app.services import registry_service
from app.workers.queue import enqueue_recovery, enqueue_resume

router = APIRouter()
logger = get_logger("discord_router")


class ApprovalDecision(BaseModel):
    approval_id: str
    status: str  # "approved" | "rejected" | "changes_requested"
    feedback: str | None = None


@router.post("/discord/approval")
async def discord_approval(payload: ApprovalDecision, x_devsync_secret: str | None = Header(default=None)):
    expected = require("DISCORD_CALLBACK_SHARED_SECRET")
    if x_devsync_secret != expected:
        return JSONResponse(status_code=401, content={"status": "error", "reason": "invalid callback secret"})

    if payload.status not in ("approved", "rejected", "changes_requested"):
        return JSONResponse(status_code=400, content={"status": "error", "reason": "unknown status"})

    try:
        approval = registry_service.decide_approval(payload.approval_id, payload.status, payload.feedback)
    except StaleApprovalError as e:
        log_error(logger, "stale approval decision rejected", exc=e, operation="decide_approval",
                  approval_id=payload.approval_id)
        return JSONResponse(status_code=409, content={"status": "error", "reason": str(e)})
    except Exception as e:
        log_error(logger, "decide_approval failed", exc=e, service="supabase", operation="decide_approval",
                  approval_id=payload.approval_id)
        return JSONResponse(status_code=502, content={"status": "error", "reason": "registry unavailable"})

    try:
        enqueue_resume(approval["workflow_id"], {
            "approval_id": payload.approval_id, "status": payload.status, "feedback": payload.feedback,
        })
    except Exception as e:
        log_error(logger, "failed to enqueue resume", exc=e, service="redis", operation="enqueue_resume",
                  workflow_id=approval["workflow_id"])
        return JSONResponse(status_code=502, content={"status": "error", "reason": "queue unavailable"})

    return {"status": "success", "workflow_id": approval["workflow_id"], "approval_id": payload.approval_id}


class WorkflowAction(BaseModel):
    workflow_id: str
    action: str  # "resume" | "cancel"
    discord_user_id: str


@router.post("/discord/workflow-action")
async def discord_workflow_action(payload: WorkflowAction, x_devsync_secret: str | None = Header(default=None)):
    """Discord Resume/Cancel on a failed, checkpointed workflow. Never trusts
    the workflow_id/action from the client without validating server-side
    state (spec §15) -- and never creates a new workflow_id or GitHub event;
    this only ever re-invokes the exact same workflow from its own
    checkpoint (spec §7/§18)."""
    expected = require("DISCORD_CALLBACK_SHARED_SECRET")
    if x_devsync_secret != expected:
        return JSONResponse(status_code=401, content={"status": "error", "reason": "invalid callback secret"})

    if payload.action not in ("resume", "cancel"):
        return JSONResponse(status_code=400, content={"status": "error", "reason": "unknown action"})

    run = registry_service.get_workflow_run(payload.workflow_id)
    if not run:
        return JSONResponse(status_code=404, content={"status": "error", "reason": "workflow not found"})
    if run["status"] != "failed" or not run.get("recoverable"):
        # Covers: already resumed, already cancelled, already completed, or
        # never actually failed -- spec §10/§9: no invalid transitions, and
        # a cancelled workflow can never be accidentally resumed afterward.
        return JSONResponse(status_code=409, content={
            "status": "error", "reason": f"workflow is not in a recoverable failed state (status={run['status']}, recoverable={run.get('recoverable')})",
        })

    if payload.action == "cancel":
        registry_service.mark_workflow_cancelled(payload.workflow_id)
        logger.info(f"workflow cancelled via discord: workflow_id={payload.workflow_id} "
                    f"discord_user_id={payload.discord_user_id}")
        return {"status": "success", "workflow_id": payload.workflow_id, "action": "cancel"}

    # action == "resume": claim the workflow so a duplicate Resume click
    # can't start a second concurrent execution of the same run (spec §9).
    claim_key = f"devsync:resume_claim:{payload.workflow_id}"
    if not acquire_claim(claim_key, ttl_seconds=120):
        return JSONResponse(status_code=409, content={
            "status": "error", "reason": "a resume for this workflow is already in progress",
        })

    try:
        registry_service.mark_workflow_resuming(payload.workflow_id)
        enqueue_recovery(payload.workflow_id)
    except Exception as e:
        log_error(logger, "failed to enqueue workflow recovery", exc=e, service="redis",
                  operation="enqueue_recovery", workflow_id=payload.workflow_id)
        return JSONResponse(status_code=502, content={"status": "error", "reason": "queue unavailable"})

    logger.info(f"workflow resume triggered via discord: workflow_id={payload.workflow_id} "
                f"failed_node={run.get('failed_node')} discord_user_id={payload.discord_user_id}")
    return {"status": "success", "workflow_id": payload.workflow_id, "action": "resume",
            "resume_node": run.get("failed_node")}
