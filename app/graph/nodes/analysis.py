from __future__ import annotations

from app.graph.util import node
from app.models.decisions import RepoAnalysis, ScoringDecision
from app.models.project import Project
from app.prompt.prompts import repo_analysis_system, repo_analysis_user, score_project_system, score_project_user
from app.services import knowledge_service, project_service
from app.services.groq_client import structured_call
from app.utils.slug import slugify


@node("analyze_repository")
def analyze_repository(state: dict) -> dict:
    project_data = dict(state["project_data"])
    analysis: RepoAnalysis = structured_call(
        repo_analysis_system(),
        repo_analysis_user(project_data["context"], project_data["readme"], state.get("commit_message", "")),
        RepoAnalysis,
        operation="analyze_repository",
    )
    project_data.update(analysis.model_dump())
    return {"current_stage": "analyzed", "project_data": project_data}


@node("structure_project_knowledge")
def structure_project_knowledge(state: dict) -> dict:
    pd = state["project_data"]
    slug = slugify(pd.get("name") or state["repository"])
    project = Project(
        owner=pd["owner"], name=pd.get("name", state["repository"]), slug=slug,
        description=pd.get("description", ""), problem=pd.get("problem", ""), solution=pd.get("solution", ""),
        technologies=pd.get("technologies", []), architecture=pd.get("architecture", ""),
        features=pd.get("features", []), technical_depth=pd.get("technical_depth", ""),
        impact=pd.get("impact", ""), completion_status=pd.get("completion_status", "in_progress"),
        category=pd.get("category", "ignore"), repository_url=pd.get("repository_url", ""),
        live_url=pd.get("live_url", ""), source_commit=pd.get("source_commit"),
        source_repository=pd.get("source_repository"),
    )

    chunk = "\n".join(filter(None, [
        project.description, project.problem, project.solution,
        "Technologies: " + ", ".join(project.technologies),
        "Features: " + "; ".join(project.features),
    ]))
    knowledge_service.index_project(project.owner, None, "repo_analysis", chunk, {"slug": slug})

    pd = {**pd, **project.model_dump(exclude={"id", "created_at", "updated_at"})}
    return {"current_stage": "structured", "project_data": pd, "project_slug": slug}


@node("retrieve_relevant_knowledge")
def retrieve_relevant_knowledge(state: dict) -> dict:
    pd = state["project_data"]
    query = f"{pd.get('name', '')} {pd.get('description', '')} {pd.get('problem', '')}"
    hits = knowledge_service.retrieve(pd["owner"], query, top_k=8)
    return {"current_stage": "retrieved", "retrieved_context": hits}


@node("score_project")
def score_project(state: dict) -> dict:
    pd = state["project_data"]
    project = Project.model_validate(pd)

    if project.category == "ignore":
        return {
            "current_stage": "scored",
            "scores": {"verdict": "REJECT", "score": 0, "reasoning": "classified as ignore", "action": "ignored"},
            "candidate_projects": [],
        }

    existing = project_service.list_projects(project.owner, category=project.category)
    decision: ScoringDecision = structured_call(
        score_project_system(),
        score_project_user(project.model_dump(), [p.model_dump() for p in existing], state.get("retrieved_context", [])),
        ScoringDecision,
        operation="score_project",
    )

    result = project_service.apply_scoring_decision(project, decision, existing)
    scores = decision.model_dump()
    scores["action"] = result["action"]
    scores["removed"] = result["removed"]

    pd = dict(pd)
    if result["project"]:
        pd["id"] = result["project"].id
        pd["score"] = result["project"].score

    return {
        "current_stage": "scored",
        "scores": scores,
        "project_data": pd,
        "candidate_projects": [p.model_dump() for p in existing],
    }
