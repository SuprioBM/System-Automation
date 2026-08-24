"""One-time initialization: reset project data only (never touches
workflow_runs/artifacts/approvals/resume_versions or anything outside
`projects`/`knowledge_chunks`), then seed the four historical featured
projects supplied by the operator, plus their pgvector RAG representations.

Run with: python -m app.db.seed_historical_projects

Per spec §45: historical projects are NOT scored against each other here --
that only happens when a genuinely new project is pushed later. They're
inserted directly as the known-good baseline.
"""
from __future__ import annotations

from app.core.config import require
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase
from app.models.project import Project
from app.services import knowledge_service, project_service

logger = get_logger("seed_historical_projects")

# Baseline score: these are pre-approved historical projects, not freshly
# LLM-scored -- assigning them all an equal, documented placeholder rather
# than fabricating a precise evaluation. Future real projects are scored for
# real by score_project and can naturally outrank or lose to this baseline.
BASELINE_SCORE = 75.0

HISTORICAL_FEATURED_PROJECTS = [
    {
        "slug": "ai-trip-planner",
        "title": "AiVoyage — AI Travel Planner",
        "description": "An AI-powered travel planning system that generates structured itineraries based on user preferences and constraints.",
        "stack": ["Next.js", "AI Integration", "Node.js"],
        "live": "https://aivoyage.vercel.app",
        "repo": "https://github.com/SuprioBM/AiTrip",
    },
    {
        "slug": "carefind-ai",
        "title": "CareFind — AI Healthcare Routing System",
        "description": "A smart healthcare platform that analyzes symptoms and helps users find relevant medical specialists.",
        "stack": ["AI Systems", "Full-Stack", "Data Modeling"],
        "live": "https://carefind.vercel.app",
        "repo": "https://github.com/SuprioBM/CareFindAi",
    },
    {
        "slug": "cv-wizard",
        "title": "CV Wizard AI — Resume Generator",
        "description": "An AI-powered tool that helps users generate structured and professional resumes quickly and easily.",
        "stack": ["React", "AI Integration", "SaaS"],
        "live": "https://cvwizardai.vercel.app",
        "repo": "https://github.com/SuprioBM/ai_sass",
    },
    {
        "slug": "fymen-ai",
        "title": "Fymen AI — AI Based Learning System",
        "description": "A full-stack AI system enabling learning through guided, progressive questioning from basic to deeper understanding.",
        "stack": ["Rag", "Next.js", "AI Systems"],
        "live": "https://fymenai.vercel.app",
        "repo": "https://github.com/SuprioBM/fynmanAI",
    },
]


def clean_project_data(owner: str) -> None:
    """Delete ONLY project records and project-linked knowledge_chunks for
    this owner. Never touches any other table."""
    s = get_supabase()
    existing = s.table("projects").select("id").eq("owner", owner).execute().data or []
    ids = [p["id"] for p in existing]
    logger.info(f"cleaning {len(ids)} existing project(s) and their knowledge_chunks for owner={owner}")
    if ids:
        s.table("knowledge_chunks").delete().in_("project_id", ids).execute()
    s.table("knowledge_chunks").delete().eq("owner", owner).is_("project_id", "null").execute()
    s.table("projects").delete().eq("owner", owner).execute()


def seed(owner: str) -> list[Project]:
    saved: list[Project] = []
    for item in HISTORICAL_FEATURED_PROJECTS:
        project = Project(
            owner=owner,
            name=item["title"],
            slug=item["slug"],
            description=item["description"],
            technologies=item["stack"],
            repository_url=item["repo"],
            live_url=item["live"],
            category="featured",
            status="active",
            completion_status="production",  # inferred from having a live URL, not fabricated
            score=BASELINE_SCORE,
        )
        row = project_service.upsert_project(project)
        saved.append(row)
        logger.info(f"seeded project: {row.slug}")

        chunk = "\n".join(filter(None, [
            row.name, row.description, "Technologies: " + ", ".join(row.technologies),
        ]))
        knowledge_service.index_project(owner, row.id, "historical_seed", chunk, {"slug": row.slug})
        logger.info(f"indexed knowledge chunk for: {row.slug}")

    return saved


def run() -> None:
    owner = require("GITHUB_OWNER")
    clean_project_data(owner)
    saved = seed(owner)
    logger.info(f"seeding complete: {len(saved)} historical projects active for owner={owner}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        log_error(logger, "historical project seeding failed", exc=e, operation="seed_historical_projects")
        raise
