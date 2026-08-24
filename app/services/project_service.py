"""Project persistence + deterministic application of scoring decisions.

The LLM (via score_project) supplies semantic judgment as a ScoringDecision;
this module is the deterministic gate that actually mutates `projects` --
it enforces slot limits and refuses to destroy a strong existing project
just because a new one showed up with a REPLACE verdict, per spec §15/§10.

Per spec §44, "featuredProjects" is the ONLY portfolio section the automated
GitHub->scoring pipeline may mutate. A project classified "insight" or
"ignore" is still scored/logged for RAG context, but never automatically
inserted/replaced in the persistent project set -- that would silently
mutate the (currently locked) Insight Projects portfolio section.
"""
from __future__ import annotations

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase
from app.models.decisions import ScoringDecision
from app.models.project import Project

logger = get_logger("project_service")

FEATURED_LIMIT = 4
AUTO_MUTABLE_CATEGORY = "featured"


def list_projects(owner: str, category: str | None = None, status: str | None = "active") -> list[Project]:
    """By default returns only status='active' projects (the current
    featured set). Pass status=None to include archived/rejected too (e.g.
    for historical RAG context or admin views)."""
    try:
        q = get_supabase().table("projects").select("*").eq("owner", owner)
        if category:
            q = q.eq("category", category)
        if status:
            q = q.eq("status", status)
        res = q.order("score", desc=True).execute()
        return [Project.model_validate(row) for row in (res.data or [])]
    except Exception as e:
        log_error(logger, "list_projects failed", exc=e, service="supabase", operation="list_projects", owner=owner)
        raise ExternalServiceError("supabase", "list_projects", str(e), original=e) from e


def upsert_project(project: Project) -> Project:
    try:
        payload = project.model_dump(exclude={"id", "created_at", "updated_at"}, mode="json")
        res = get_supabase().table("projects").upsert(payload, on_conflict="slug").execute()
        return Project.model_validate(res.data[0])
    except Exception as e:
        log_error(logger, "upsert_project failed", exc=e, service="supabase", operation="upsert_project",
                  slug=project.slug)
        raise ExternalServiceError("supabase", "upsert_project", str(e), original=e) from e


def archive_project(project_id: str) -> None:
    """Mark a project archived (replaced by a stronger one) rather than
    deleting it -- preserves it for historical/RAG context per spec §48."""
    try:
        get_supabase().table("projects").update({"status": "archived"}).eq("id", project_id).execute()
    except Exception as e:
        log_error(logger, "archive_project failed", exc=e, service="supabase", operation="archive_project",
                  project_id=project_id)
        raise ExternalServiceError("supabase", "archive_project", str(e), original=e) from e


def delete_project(project_id: str) -> None:
    """Hard delete -- not used by the automated scoring pipeline (which
    archives instead); kept for explicit admin/cleanup use."""
    try:
        get_supabase().table("projects").delete().eq("id", project_id).execute()
    except Exception as e:
        log_error(logger, "delete_project failed", exc=e, service="supabase", operation="delete_project",
                  project_id=project_id)
        raise ExternalServiceError("supabase", "delete_project", str(e), original=e) from e


def apply_scoring_decision(new_project: Project, decision: ScoringDecision, existing: list[Project]) -> dict:
    """Deterministically apply a ScoringDecision. Returns {"action": ..., "project": Project|None, "removed": str|None}."""
    if decision.verdict == "REJECT":
        return {"action": "rejected", "project": None, "removed": None}

    if new_project.category != AUTO_MUTABLE_CATEGORY:
        # "insight"/"ignore": scored for context, but only Featured Projects
        # may be automatically added/replaced (spec §44). No Supabase write.
        return {"action": "not_auto_mutable_category", "project": None, "removed": None}

    same_category = [p for p in existing if p.category == new_project.category]

    if decision.verdict in ("ADD", "KEEP") and len(same_category) < FEATURED_LIMIT:
        new_project.score = decision.score
        new_project.status = "active"
        saved = upsert_project(new_project)
        return {"action": "inserted", "project": saved, "removed": None}

    # REPLACE, or ADD/KEEP with no free slot: only proceed if strictly better
    # than the weakest current holder -- never destroy a strong project just
    # because a new one exists.
    if not same_category:
        new_project.score = decision.score
        new_project.status = "active"
        saved = upsert_project(new_project)
        return {"action": "inserted", "project": saved, "removed": None}

    weakest = min(same_category, key=lambda p: p.score)
    if decision.score <= weakest.score:
        return {"action": "rejected_not_strong_enough", "project": None, "removed": None}

    if weakest.id:
        archive_project(weakest.id)  # preserved, not deleted -- see module docstring
    new_project.score = decision.score
    new_project.status = "active"
    saved = upsert_project(new_project)
    return {"action": "replaced", "project": saved, "removed": weakest.slug}
