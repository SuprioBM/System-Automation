import pytest

from app.models.decisions import ScoringDecision
from app.models.project import Project
from app.services import project_service


def _project(slug="new-project", category="featured", score=0.0) -> Project:
    return Project(owner="octocat", name=slug, slug=slug, category=category, score=score)


def _decision(verdict="ADD", score=80.0, replace_slug=None) -> ScoringDecision:
    return ScoringDecision(
        verdict=verdict, score=score, relevance_to_role=8, technical_depth=8, uniqueness=8,
        ai_agentic_relevance=8, completeness=8, replace_candidate_slug=replace_slug, reasoning="test",
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    saved = {}
    monkeypatch.setattr(project_service, "upsert_project", lambda p: (saved.setdefault("saved", p), p)[1])
    monkeypatch.setattr(project_service, "archive_project", lambda pid: saved.setdefault("archived", pid))
    return saved


def test_reject_verdict_never_persists():
    result = project_service.apply_scoring_decision(_project(), _decision("REJECT"), existing=[])
    assert result["action"] == "rejected"
    assert result["project"] is None


def test_adds_when_slot_available():
    result = project_service.apply_scoring_decision(_project(), _decision("ADD", 80), existing=[])
    assert result["action"] == "inserted"


def test_refuses_to_replace_a_stronger_existing_project():
    strong = Project(owner="octocat", name="strong", slug="strong", category="featured", score=95, id="1")
    existing = [strong] * project_service.FEATURED_LIMIT
    result = project_service.apply_scoring_decision(_project(score=0), _decision("REPLACE", 40), existing=existing)
    assert result["action"] == "rejected_not_strong_enough"
    assert result["project"] is None


def test_replaces_the_weakest_project_when_strictly_better(no_network):
    weak = Project(owner="octocat", name="weak", slug="weak", category="featured", score=10, id="1")
    others = [Project(owner="octocat", name=f"p{i}", slug=f"p{i}", category="featured", score=90, id=str(i))
              for i in range(project_service.FEATURED_LIMIT - 1)]
    existing = [weak] + others
    result = project_service.apply_scoring_decision(_project(score=0), _decision("REPLACE", 50), existing=existing)
    assert result["action"] == "replaced"
    assert result["removed"] == "weak"
    # replaced, not deleted -- preserved for history/RAG (spec §48)
    assert no_network["archived"] == "1"


def test_ignore_category_never_mutates_storage(no_network):
    result = project_service.apply_scoring_decision(_project(category="ignore"), _decision("ADD", 80), existing=[])
    assert result["action"] == "not_auto_mutable_category"
    assert "saved" not in no_network


def test_insight_category_never_auto_mutates_storage(no_network):
    """Spec §44: Insight Projects is a locked portfolio section -- only
    'featured' may be automatically added/replaced."""
    result = project_service.apply_scoring_decision(_project(category="insight"), _decision("ADD", 95), existing=[])
    assert result["action"] == "not_auto_mutable_category"
    assert "saved" not in no_network
