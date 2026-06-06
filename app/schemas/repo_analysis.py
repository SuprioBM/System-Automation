from pydantic import BaseModel


class RepoAnalysis(BaseModel):
    project_score: int
    impact_level: str
    summary: str
    skills_used: list[str]
    portfolio_recommendation: bool
    resume_bullets: list[str]
    linkedin_angle: str
    tags: list[str]