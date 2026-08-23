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
from app.services import registry_service
from app.workers.queue import enqueue_resume

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
