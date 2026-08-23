from __future__ import annotations

from fastapi import APIRouter

from app.core import redis_client
from app.core.errors import ExternalServiceError
from app.core.supabase import get_supabase

router = APIRouter()


@router.get("/health")
async def health():
    components = {}

    try:
        redis_client.ping()
        components["redis"] = "ok"
    except ExternalServiceError as e:
        components["redis"] = f"error: {e}"

    try:
        get_supabase().table("workflow_runs").select("workflow_id").limit(1).execute()
        components["supabase"] = "ok"
    except Exception as e:
        components["supabase"] = f"error: {e}"

    healthy = all(v == "ok" for v in components.values())
    return {"status": "ok" if healthy else "degraded", "components": components}
