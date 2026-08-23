from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.services import portfolio_service

router = APIRouter(prefix="/portfolio")
logger = get_logger("portfolio_router")


@router.post("/revalidate")
async def revalidate(secret: str):
    if secret != settings.REVALIDATE_SECRET:
        return JSONResponse(status_code=401, content={"status": "error", "reason": "invalid secret"})
    try:
        portfolio_service.trigger_revalidate()
    except ExternalServiceError as e:
        log_error(logger, "manual revalidate failed", exc=e, service="portfolio_site", operation="revalidate")
        return JSONResponse(status_code=502, content={"status": "error", "reason": str(e)})
    return {"status": "success"}
