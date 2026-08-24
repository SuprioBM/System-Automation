from __future__ import annotations

import uuid

from app.core.logging import get_logger, log_error
from app.graph.util import node

logger = get_logger("generate_artifacts")
from app.models.decisions import GeneratedCopy
from app.models.project import Project
from app.prompt.prompts import generate_copy_system, generate_copy_user
from app.services import project_service, resume_service, skills_service, storage_service
from app.services.groq_client import structured_call
from app.services.pollinations_service import generate_image


@node("generate_artifacts")
def generate_artifacts(state: dict) -> dict:
    approval_state = state.get("approval_state") or {}
    existing_outputs = dict(state.get("generated_outputs") or {})

    if approval_state:
        # Regeneration pass (a human clicked "request changes" on one
        # artifact type): only redo the type(s) actually flagged.
        # Artifact types that are already approved/rejected/still-pending
        # must not be regenerated or re-sent -- that would silently
        # re-litigate a decision the human already made (or re-spam a
        # pending one with a duplicate draft).
        selected = [k for k, v in approval_state.items() if v.get("status") == "changes_requested"]
    else:
        selected = state.get("selected_actions", [])

    if not selected:
        return {"current_stage": "generated", "generated_outputs": existing_outputs, "_regenerated_types": []}

    project = Project.model_validate(state["project_data"])
    feedback = (state.get("approval_feedback") or {}).get("_last_feedback")
    outputs: dict = dict(existing_outputs)

    copy: GeneratedCopy | None = None
    if "resume" in selected or "linkedin" in selected:
        copy = structured_call(
            generate_copy_system(), generate_copy_user(project.model_dump(), feedback),
            GeneratedCopy, operation="generate_copy",
        )

    if "portfolio" in selected:
        outputs["portfolio"] = {
            "project": project.model_dump(),
            "action": state["scores"].get("action"),
            "removed": state["scores"].get("removed"),
        }

    if "resume" in selected and copy:
        featured = project_service.list_projects(project.owner, "featured")
        # Build on top of whatever résumé is currently active (or the blank
        # template if none is active yet) and touch ONLY the Featured
        # slots -- insight=None leaves Insight Projects (and everything
        # else) exactly as it already is. The automated pipeline never
        # regenerates that section; per spec §44 only Featured Projects is
        # automatically mutable.
        base_tex = resume_service.get_base_document()
        candidate_tex = resume_service.render_tex(base_tex, featured=featured, insight=None)

        # Skills is the one other section DevSync may touch, and only under
        # strict constraints enforced in skills_service (no new categories,
        # capped length, canonicalized dedup) -- everything else in the
        # document stays exactly as get_base_document() provided it.
        skills_recommendations: list[str] = []
        try:
            candidate_tex, skills_recommendations = skills_service.apply_to_tex(candidate_tex, project.model_dump())
        except Exception as e:
            # A failed skills proposal must not block the resume regeneration
            # itself -- the featured-slot update is still valid without it.
            log_error(logger, "skills update proposal failed, resume slots unaffected", exc=e,
                      service="groq", operation="skills_update", workflow_id=state.get("workflow_id"))

        outputs["resume"] = {
            "tex": candidate_tex, "bullets": copy.resume_bullets,
            "skills_recommendations": skills_recommendations,
        }

    if "linkedin" in selected and copy:
        image_url = None
        try:
            image_bytes = generate_image(f"{project.name}: {copy.linkedin_angle}. Clean modern tech illustration.")
            image_url = storage_service.upload_bytes(f"linkedin/{uuid.uuid4()}.png", image_bytes, "image/png")
        except Exception as e:
            # Image generation is best-effort -- a missing image must not block the text
            # post, but the failure is still logged, never swallowed silently.
            log_error(logger, "linkedin image generation failed, continuing without image", exc=e,
                      service="pollinations", operation="generate_image",
                      workflow_id=state.get("workflow_id"))
        outputs["linkedin"] = {"post": copy.linkedin_post, "angle": copy.linkedin_angle, "image_url": image_url}

    return {"current_stage": "generated", "generated_outputs": outputs, "_regenerated_types": selected}
