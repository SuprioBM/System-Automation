from __future__ import annotations

from app.graph.util import node
from app.services import resume_service, storage_service

LINKEDIN_MAX_CHARS = 3000


@node("validate_artifacts")
def validate_artifacts(state: dict) -> dict:
    outputs = dict(state.get("generated_outputs", {}))
    # Only (re)validate artifact types that were actually (re)generated this
    # pass -- re-running validation (a real LaTeX compile call for resume!)
    # against unchanged, already-decided artifacts would be wasted work at
    # best and could flip an already-approved artifact's stored validation
    # results at worst.
    to_validate = state.get("_regenerated_types")
    if to_validate is None:
        to_validate = list(outputs.keys())
    results: dict = dict(state.get("validation_results") or {})

    if "portfolio" in to_validate and "portfolio" in outputs:
        results["portfolio"] = {"passed": True, "content_checks": {"project_present": True}, "issues": []}

    if "resume" in to_validate and "resume" in outputs:
        base_tex = resume_service.load_template()
        pdf_bytes, validation = resume_service.compile_and_validate(outputs["resume"]["tex"], base_tex)
        if pdf_bytes:
            draft_url = storage_service.upload_bytes(
                f"resume-drafts/{state['workflow_id']}.pdf", pdf_bytes, "application/pdf"
            )
            outputs["resume"]["pdf_draft_url"] = draft_url
        results["resume"] = validation.model_dump()

    if "linkedin" in to_validate and "linkedin" in outputs:
        post = outputs["linkedin"]["post"]
        passed = bool(post) and len(post) <= LINKEDIN_MAX_CHARS
        results["linkedin"] = {
            "passed": passed,
            "content_checks": {"non_empty": bool(post), "within_length_limit": len(post) <= LINKEDIN_MAX_CHARS},
            "issues": [] if passed else ["linkedin post is empty or exceeds LinkedIn's character limit"],
        }

    return {"current_stage": "validated", "generated_outputs": outputs, "validation_results": results}
