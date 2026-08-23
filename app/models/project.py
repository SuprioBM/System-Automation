from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["featured", "insight", "ignore"]
CompletionStatus = Literal["prototype", "in_progress", "complete", "production"]


class Project(BaseModel):
    """Canonical structured project record -- mirrors the `projects` table.
    This is the source of truth; knowledge_chunks (pgvector) is a derived
    retrieval index over this and other text, never the other way around.
    """

    id: str | None = None
    owner: str
    name: str
    slug: str
    description: str = ""
    problem: str = ""
    solution: str = ""
    technologies: list[str] = Field(default_factory=list)
    architecture: str = ""
    features: list[str] = Field(default_factory=list)
    technical_depth: str = ""
    impact: str = ""
    completion_status: CompletionStatus = "in_progress"
    category: Category = "ignore"
    score: float = 0.0
    resume_bullets: list[str] = Field(default_factory=list)
    linkedin_angle: str = ""
    repository_url: str = ""
    live_url: str = ""
    source_commit: str | None = None
    source_repository: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
