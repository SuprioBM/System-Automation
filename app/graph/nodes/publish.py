from __future__ import annotations

import requests

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.graph.util import node
from app.models.decisions import ArtifactValidation
from app.services import linkedin_service, portfolio_service, registry_service, resume_service

logger = get_logger("publish_nodes")


@node("publish")
def publish(state: dict) -> dict:
    approval_state = state.get("approval_state", {})
    outputs = state.get("generated_outputs", {})
    validation = state.get("validation_results", {})
    published: dict = {}

    if approval_state.get("resume", {}).get("status") == "approved":
        try:
            pdf_url = outputs["resume"]["pdf_draft_url"]
            pdf_bytes = requests.get(pdf_url, timeout=30).content
            final_url = resume_service.store_pdf(pdf_bytes, resume_service.next_version())
            v = ArtifactValidation.model_validate(validation.get("resume", {}))
            row = resume_service.save_version(final_url, outputs["resume"]["tex"], v, state["artifacts"].get("resume"))
            resume_service.activate_version(row["id"])
            published["resume"] = final_url
        except Exception as e:
            log_error(logger, "resume publish failed", exc=e, service="resume_service", operation="publish",
                      workflow_id=state.get("workflow_id"))

    if approval_state.get("linkedin", {}).get("status") == "approved":
        try:
            image_bytes = None
            image_url = outputs.get("linkedin", {}).get("image_url")
            if image_url:
                res = requests.get(image_url, timeout=30)
                image_bytes = res.content if res.status_code == 200 else None
            result = linkedin_service.publish_post(outputs["linkedin"]["post"], image_bytes)
            published["linkedin"] = result.get("post_id")
        except Exception as e:
            log_error(logger, "linkedin publish failed", exc=e, service="linkedin", operation="publish",
                      workflow_id=state.get("workflow_id"))

    if approval_state.get("portfolio", {}).get("status") == "approved":
        published["portfolio"] = True

    if published:
        try:
            portfolio_service.trigger_revalidate()
        except ExternalServiceError as e:
            log_error(logger, "portfolio revalidate failed (published content is still live in Supabase)", exc=e,
                      service="portfolio_site", operation="revalidate", workflow_id=state.get("workflow_id"))

    return {"current_stage": "published", "generated_outputs": {**outputs, "_published": published}}


@node("finalize_workflow")
def finalize_workflow(state: dict) -> dict:
    approval_state = state.get("approval_state", {})
    scores_action = state.get("scores", {}).get("action")

    if any(v.get("status") == "approved" for v in approval_state.values()):
        status = "completed"
    elif approval_state and all(v.get("status") == "rejected" for v in approval_state.values()):
        status = "rejected"
    elif scores_action in ("rejected", "rejected_not_strong_enough", "ignored"):
        status = "rejected"
    else:
        status = "failed"

    if state.get("workflow_id"):
        fields = {"status": status, "current_stage": "finalized"}
        if status != "failed":
            # Clear any error_state left over from an earlier failed node in
            # this same run that a later retry/resume then got past --
            # otherwise a workflow that succeeded on retry still shows the
            # stale failure from its first attempt forever.
            fields["error_state"] = None
        registry_service.update_workflow_run(state["workflow_id"], **fields)

    return {"current_stage": "published" if status == "completed" else "rejected" if status == "rejected" else "failed"}
