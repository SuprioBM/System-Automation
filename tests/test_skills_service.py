from app.models.decisions import SkillCategoryUpdate, SkillsUpdate
from app.services import skills_service


def _current():
    return {
        "Frontend Architecture": ["React", "Next.js", "Tailwind CSS", "JavaScript"],
        "Backend & Distributed Systems": ["Node.js", "Express.js", "PostgreSQL"],
        "AI & Machine Learning Systems": ["OpenAI APIs", "RAG Systems"],
        "Infrastructure & DevOps": ["Git", "GitHub", "Docker"],
    }


def test_rejects_unknown_category():
    current = _current()
    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(category="Mobile Development", skills=["Swift"], reasoning="new category attempt"),
    ])
    accepted, recs = skills_service._enforce_hard_rules(current, proposal)
    assert accepted == {}  # never creates a new category


def test_applies_genuine_new_skill_to_existing_category():
    current = _current()
    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(
            category="Frontend Architecture",
            skills=["React", "Next.js", "Tailwind CSS", "JavaScript", "TypeScript"],
            reasoning="project genuinely uses TypeScript",
        ),
    ])
    accepted, recs = skills_service._enforce_hard_rules(current, proposal)
    assert accepted["Frontend Architecture"] == ["React", "Next.js", "Tailwind CSS", "JavaScript", "TypeScript"]
    assert recs == []


def test_safety_net_dedupes_exact_case_insensitive_repeats():
    """Semantic canonicalization ("NodeJS" -> "Node.js") is the LLM's job
    (see the prompt's rule 3) -- this deterministic layer is only a safety
    net against the model literally repeating the same string twice."""
    current = _current()
    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(
            category="Backend & Distributed Systems",
            skills=["Node.js", "node.js", "Express.js", "PostgreSQL", "Redis"],
            reasoning="add redis",
        ),
    ])
    accepted, recs = skills_service._enforce_hard_rules(current, proposal)
    assert accepted["Backend & Distributed Systems"] == ["Node.js", "Express.js", "PostgreSQL", "Redis"]


def test_over_cap_proposal_is_not_applied_and_produces_recommendation():
    current = _current()
    too_many = [f"skill-{i}" for i in range(skills_service.MAX_SKILLS_PER_CATEGORY + 3)]
    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(category="Infrastructure & DevOps", skills=too_many, reasoning="too many"),
    ])
    accepted, recs = skills_service._enforce_hard_rules(current, proposal)
    assert "Infrastructure & DevOps" not in accepted
    assert len(recs) == 1
    assert "layout-safe limit" in recs[0]


def test_no_change_when_proposal_matches_existing():
    current = _current()
    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(category="Frontend Architecture", skills=current["Frontend Architecture"], reasoning="no change"),
    ])
    accepted, recs = skills_service._enforce_hard_rules(current, proposal)
    assert accepted == {}  # identical list -> not treated as a change


def test_apply_to_tex_only_touches_changed_slot(monkeypatch):
    from app.services import resume_service

    base = resume_service.load_template()
    current = skills_service.get_current_skills(base)
    assert current["Frontend Architecture"] == [
        "React", "Next.js", "TypeScript", "Tailwind CSS", "JavaScript (ES6+)", "HTML5", "CSS3", "Responsive UI Design",
    ]

    proposal = SkillsUpdate(categories=[
        SkillCategoryUpdate(
            category="AI & Machine Learning Systems",
            skills=current["AI & Machine Learning Systems"] + ["LangGraph"],
            reasoning="project uses LangGraph",
        ),
    ])
    monkeypatch.setattr(skills_service, "propose_update", lambda project, existing: proposal)

    new_tex, recs = skills_service.apply_to_tex(base, {"name": "test"})
    assert "LangGraph" in new_tex
    # every other category's exact original text is untouched
    assert "React, Next.js, TypeScript, Tailwind CSS" in new_tex
    assert "Node.js, Express.js, PostgreSQL, MongoDB" in new_tex
