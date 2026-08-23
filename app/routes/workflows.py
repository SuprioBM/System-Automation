from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.supabase import get_supabase
from app.services import registry_service

router = APIRouter(prefix="/workflows")


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    run = registry_service.get_workflow_run(workflow_id)
    if not run:
        return JSONResponse(status_code=404, content={"status": "error", "reason": "workflow not found"})

    artifacts = get_supabase().table("artifacts").select("*").eq("workflow_id", workflow_id).execute().data or []
    approvals = get_supabase().table("approvals").select("*").eq("workflow_id", workflow_id).execute().data or []
    return {"workflow": run, "artifacts": artifacts, "approvals": approvals}
