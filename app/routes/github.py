"""GitHub App webhook receiver. Thin and fast on purpose: verify signature,
check idempotency, enqueue -- the actual AI workflow always runs in the
worker (via LangGraph), never synchronously in this request handler.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.core.errors import ConfigurationError
from app.core.logging import get_logger, log_error
from app.services import github_app, registry_service
from app.utils.extract_commit import extract_commit_message
from app.utils.extract_repoName import extract_repo_name
from app.workers.queue import enqueue_new_workflow

router = APIRouter()
logger = get_logger("github_webhook")


@router.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()

    try:
        valid = github_app.verify_webhook_signature(body, x_hub_signature_256)
    except ConfigurationError as e:
        log_error(logger, "webhook signature check misconfigured", exc=e, operation="verify_webhook_signature")
        return JSONResponse(status_code=500, content={"status": "error", "reason": str(e)})

    if not valid:
        log_error(logger, "webhook signature verification failed", exc=None,
                  operation="verify_webhook_signature", delivery_id=x_github_delivery)
        return JSONResponse(status_code=401, content={"status": "error", "reason": "invalid signature"})

    try:
        payload = json.loads(body)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"status": "error", "reason": "invalid JSON", "error": str(e)})

    if x_github_event != "push":
        return {"status": "ignored", "reason": f"event type '{x_github_event}' is not handled"}

    commit_message = extract_commit_message(payload)
    repository = extract_repo_name(payload)
    commit_sha = (payload.get("head_commit") or {}).get("id", "")
    installation_id = (payload.get("installation") or {}).get("id")
    pusher = (payload.get("pusher") or {}).get("name") or (payload.get("sender") or {}).get("login") or ""

    if not repository or not commit_sha:
        return {"status": "error", "reason": "payload missing repository or commit"}

    if not github_app.is_final_commit(commit_message):
        return {"status": "ignored", "reason": "not a DevSync final/publish commit"}

    event_id = x_github_delivery or f"{repository}:{commit_sha}"
    try:
        if registry_service.is_duplicate_event(event_id):
            return {"status": "ignored", "reason": "duplicate delivery", "event_id": event_id}

        workflow_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
        registry_service.record_event(event_id, x_github_delivery, "github", workflow_id)
        registry_service.create_workflow_run(workflow_id, run_id, event_id, repository, commit_sha)
    except Exception as e:
        log_error(logger, "idempotency/registry bookkeeping failed", exc=e, service="supabase",
                  operation="create_workflow_run", repository=repository, commit=commit_sha)
        return JSONResponse(status_code=502, content={"status": "error", "reason": "registry unavailable"})

    initial_state = {
        "workflow_id": workflow_id, "run_id": run_id, "event_id": event_id,
        "repository": repository, "commit": commit_sha, "commit_message": commit_message,
        "user": pusher, "installation_id": installation_id, "retry_count": 0,
        "raw_event": {"delivery_id": x_github_delivery, "event": x_github_event},
    }

    try:
        enqueue_new_workflow(initial_state)
    except Exception as e:
        log_error(logger, "failed to enqueue workflow", exc=e, service="redis", operation="enqueue_new_workflow",
                  workflow_id=workflow_id)
        registry_service.update_workflow_run(workflow_id, status="failed")
        return JSONResponse(status_code=502, content={"status": "error", "reason": "queue unavailable"})

    return {"status": "accepted", "workflow_id": workflow_id, "run_id": run_id}
