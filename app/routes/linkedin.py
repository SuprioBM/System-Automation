"""LinkedIn OAuth flow. GET /linkedin/authorize starts it; GET /linkedin/callback
exchanges the code and returns the access token + person URN for the operator
to place into .env as LINKEDIN_ACCESS_TOKEN / LINKEDIN_PERSON_URN -- this
system does not persist OAuth tokens itself (see README for why)."""
from __future__ import annotations

import secrets

from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.logging import get_logger, log_error
from app.services import linkedin_service

router = APIRouter(prefix="/linkedin")
logger = get_logger("linkedin_router")


@router.get("/authorize")
async def authorize():
    return RedirectResponse(linkedin_service.get_authorize_url(secrets.token_urlsafe(16)))


@router.get("/callback")
async def callback(code: str, state: str | None = None):
    try:
        token_data = linkedin_service.exchange_code_for_token(code)
        person_urn = linkedin_service.get_person_urn(token_data["access_token"])
    except Exception as e:
        log_error(logger, "linkedin oauth callback failed", exc=e, service="linkedin", operation="callback")
        return JSONResponse(status_code=502, content={"status": "error", "reason": str(e)})

    return {
        "status": "success",
        "message": "Copy these into .env as LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN, then restart the API/worker.",
        "access_token": token_data["access_token"],
        "expires_in": token_data.get("expires_in"),
        "person_urn": person_urn,
    }
