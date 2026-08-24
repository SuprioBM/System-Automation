"""Conditional, tightly-constrained Technical Skills section updates.

Unlike Featured Projects (fully DevSync-controlled) and every other resume/
portfolio section (fully locked), the skills section is a deliberate middle
ground: DevSync may update the skill *items* within the existing categories
when a new project demonstrates a genuinely new, non-redundant,
category-appropriate skill -- but may never rename/add/remove a category,
and is capped so the résumé layout can't break. The LLM proposes a full
revised list per affected category; every hard rule below is enforced here
in code, never trusted from the model's output alone.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.models.decisions import SkillsUpdate
from app.prompt.prompts import skills_update_system, skills_update_user
from app.services import latex_slots
from app.services.groq_client import structured_call

logger = get_logger("skills_service")

MAX_SKILLS_PER_CATEGORY = 10

# Fixed, ordered list matching resume.tex's DEVSYNC_SKILLS_SLOT_1..4 markers
# by position. Never reorder without updating the template to match --
# these category names themselves are protected (rule 9): DevSync may never
# rename, add, remove, or reorder them.
SKILL_CATEGORIES = [
    "Frontend Architecture",
    "Backend & Distributed Systems",
    "AI & Machine Learning Systems",
    "Infrastructure & DevOps",
]


def get_current_skills(base_tex: str) -> dict[str, list[str]]:
    skills = {}
    for i, category in enumerate(SKILL_CATEGORIES, start=1):
        raw = latex_slots.get_slot(base_tex, "skills", i)
        skills[category] = [s.strip() for s in raw.strip().split(",") if s.strip()]
    return skills


def propose_update(project: dict, current_skills: dict[str, list[str]]) -> SkillsUpdate:
    return structured_call(
        skills_update_system(MAX_SKILLS_PER_CATEGORY),
        skills_update_user(project, current_skills),
        SkillsUpdate,
        operation="skills_update",
    )


def _enforce_hard_rules(
    current_skills: dict[str, list[str]], proposal: SkillsUpdate
) -> tuple[dict[str, list[str]], list[str]]:
    """Returns (accepted_skills_by_category, recommendations-for-humans).
    Every category name and list length is re-validated here -- the LLM's
    proposal is a suggestion, not a trusted mutation."""
    accepted: dict[str, list[str]] = {}
    recommendations: list[str] = []

    for cat_update in proposal.categories:
        if cat_update.category not in SKILL_CATEGORIES:
            logger.warning(f"skills update proposed unknown category '{cat_update.category}', ignored")
            continue

        cleaned: list[str] = []
        seen_lower: set[str] = set()
        for s in cat_update.skills:
            s = s.strip()
            if not s or s.lower() in seen_lower:
                continue
            seen_lower.add(s.lower())
            cleaned.append(s)

        if len(cleaned) > MAX_SKILLS_PER_CATEGORY:
            recommendations.append(
                f"{cat_update.category}: proposed {len(cleaned)} skills, over the "
                f"{MAX_SKILLS_PER_CATEGORY}-item layout-safe limit -- not auto-applied. "
                f"Consider consolidating a weaker existing entry first."
            )
            continue  # keep the existing list for this category untouched

        if cleaned and cleaned != current_skills.get(cat_update.category, []):
            accepted[cat_update.category] = cleaned

    return accepted, recommendations


def apply_to_tex(base_tex: str, project: dict) -> tuple[str, list[str]]:
    """Returns (updated_tex, recommendations). Only the slot(s) that
    actually changed are touched -- every other category, and everything
    outside the skills section, is left byte-for-byte alone."""
    current_skills = get_current_skills(base_tex)
    proposal = propose_update(project, current_skills)
    accepted, recommendations = _enforce_hard_rules(current_skills, proposal)

    tex = base_tex
    for i, category in enumerate(SKILL_CATEGORIES, start=1):
        if category in accepted:
            tex = latex_slots.set_slot(tex, "skills", i, ", ".join(accepted[category]))

    return tex, recommendations
