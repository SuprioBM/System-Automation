"""Project persistence + deterministic application of scoring decisions.

The LLM (via score_project) supplies semantic judgment as a ScoringDecision;
this module is the deterministic gate that actually mutates `projects` --
it enforces slot limits and refuses to destroy a strong existing project
just because a new one showed up with a REPLACE verdict, per spec §15/§10.
"""
from __future__ import annotations

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase
from app.models.decisions import ScoringDecision
from app.models.project import Project

logger = get_logger("project_service")

FEATURED_LIMIT = 4
INSIGHT_LIMIT = 6
_LIMITS = {"featured": FEATURED_LIMIT, "insight": INSIGHT_LIMIT}


def list_projects(owner: str, category: str | None = None) -> list[Project]:
    try:
        q = get_supabase().table("projects").select("*").eq("owner", owner)
        if category:
            q = q.eq("category", category)
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


def delete_project(project_id: str) -> None:
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

    if new_project.category not in _LIMITS:
        # "ignore" category or anything outside featured/insight never mutates storage.
        return {"action": "ignored", "project": None, "removed": None}

    limit = _LIMITS[new_project.category]
    same_category = [p for p in existing if p.category == new_project.category]

    if decision.verdict in ("ADD", "KEEP") and len(same_category) < limit:
        new_project.score = decision.score
        saved = upsert_project(new_project)
        return {"action": "inserted", "project": saved, "removed": None}

    # REPLACE, or ADD/KEEP with no free slot: only proceed if strictly better
    # than the weakest current holder -- never destroy a strong project just
    # because a new one exists.
    if not same_category:
        new_project.score = decision.score
        saved = upsert_project(new_project)
        return {"action": "inserted", "project": saved, "removed": None}

    weakest = min(same_category, key=lambda p: p.score)
    if decision.score <= weakest.score:
        return {"action": "rejected_not_strong_enough", "project": None, "removed": None}

    if weakest.id:
        delete_project(weakest.id)
    new_project.score = decision.score
    saved = upsert_project(new_project)
    return {"action": "replaced", "project": saved, "removed": weakest.slug}
