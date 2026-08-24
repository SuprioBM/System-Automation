"""Structured LLM output schemas. The LLM is never trusted with free text for
a decision that drives application behavior -- every judgment call it makes
is forced through one of these Pydantic models (via
ChatGroq.with_structured_output), and deterministic code in the graph nodes
is what actually acts on the result.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["featured", "insight", "ignore"]
ScoreVerdict = Literal["KEEP", "ADD", "REPLACE", "REJECT"]
ApprovalAction = Literal["approve", "reject", "changes_requested"]
RouteTarget = Literal["portfolio", "resume", "linkedin", "none"]


class RepoAnalysis(BaseModel):
    """Output of the analyze_repository node: what is this project, in the
    structured project-data-model shape (spec §14), not free prose."""

    name: str
    description: str
    problem: str
    solution: str
    technologies: list[str]
    architecture: str
    features: list[str]
    technical_depth: str = Field(description="brief assessment of engineering depth")
    impact: str
    completion_status: Literal["prototype", "in_progress", "complete", "production"]
    category: Category
    reason: str = Field(description="why this category was chosen")


class GeneratedCopy(BaseModel):
    """Output of the generate_artifact node's copy-writing step."""

    resume_bullets: list[str]
    linkedin_post: str
    linkedin_angle: str


class ScoringDecision(BaseModel):
    """Output of score_project: a structured, auditable verdict. The LLM
    supplies semantic judgment (uniqueness, depth, relevance); deterministic
    code enforces the hard constraints (slot limits, "never silently destroy
    a strong existing project")."""

    verdict: ScoreVerdict
    score: float = Field(ge=0, le=100)
    relevance_to_role: float = Field(ge=0, le=10)
    technical_depth: float = Field(ge=0, le=10)
    uniqueness: float = Field(ge=0, le=10)
    ai_agentic_relevance: float = Field(ge=0, le=10)
    completeness: float = Field(ge=0, le=10)
    overlaps_with: list[str] = Field(default_factory=list, description="slugs of existing projects this overlaps with")
    replace_candidate_slug: str | None = None
    reasoning: str


class RouteDecision(BaseModel):
    """Output of route_action: which downstream artifact(s) this project
    should produce, decided semantically but constrained to the fixed set of
    valid targets."""

    targets: list[RouteTarget]
    reasoning: str


class ArtifactValidation(BaseModel):
    """Structured validation verdict attached to any generated artifact."""

    passed: bool
    technical_checks: dict[str, bool] = Field(default_factory=dict)
    content_checks: dict[str, bool] = Field(default_factory=dict)
    quality_checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    is_improvement_over_active: bool | None = None


class SkillCategoryUpdate(BaseModel):
    """One existing skill category's proposed resulting skill list. The
    category name must exactly match an existing category -- deterministic
    code (skills_service) rejects anything else rather than trusting it."""

    category: str = Field(description="must exactly match one of the existing category names given, verbatim")
    skills: list[str] = Field(description="the FULL resulting list for this category after merging/canonicalizing, not just the additions")
    reasoning: str


class SkillsUpdate(BaseModel):
    """Output of the skills-update proposal. Only include categories whose
    skill list should actually change; omit unaffected categories entirely."""

    categories: list[SkillCategoryUpdate] = Field(default_factory=list)
