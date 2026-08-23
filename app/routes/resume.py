from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger, log_error
from app.services import project_service, resume_service, storage_service

router = APIRouter(prefix="/resume")
logger = get_logger("resume_router")


@router.get("/active")
async def active_resume():
    active = resume_service.get_active_resume()
    if not active:
        return JSONResponse(status_code=404, content={"status": "error", "reason": "no active resume yet"})
    return active


@router.post("/preview")
async def preview_resume(owner: str):
    """Dev-only: compiles a candidate résumé from real, currently-stored
    projects (no dummy data) without publishing/activating it -- useful for
    exercising the remote-compile + validation pipeline manually."""
    if settings.ENVIRONMENT != "development":
        return JSONResponse(status_code=403, content={"status": "error", "reason": "preview is dev-only"})

    featured = project_service.list_projects(owner, "featured")
    insight = project_service.list_projects(owner, "insight")
    base_tex = resume_service.load_template()
    candidate_tex = resume_service.render_tex(base_tex, featured, insight)

    try:
        pdf_bytes, validation = resume_service.compile_and_validate(candidate_tex, base_tex)
    except Exception as e:
        log_error(logger, "resume preview compile failed", exc=e, service="ytotech", operation="preview_resume")
        return JSONResponse(status_code=502, content={"status": "error", "reason": str(e)})

    if not pdf_bytes:
        return {"status": "failed_validation", "validation": validation.model_dump()}

    url = storage_service.upload_bytes(f"resume-previews/{uuid.uuid4()}.pdf", pdf_bytes, "application/pdf")
    return {"status": "ok", "validation": validation.model_dump(), "preview_url": url}
