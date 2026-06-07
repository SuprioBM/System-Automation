from fastapi import APIRouter
from app.services.pdf_generate import generate_resume_pipeline

router = APIRouter()


# -------------------------
# LOAD TEMPLATE
# -------------------------
def load_tex():
    with open("app/resume/resume.tex", "r", encoding="utf-8") as f:
        return f.read()


# -------------------------
# DUMMY DATA (IMPORTANT)
# -------------------------
def dummy_featured():
    return [
        {
            "title": "AiVoyage — AI Travel Planner",
            "live": "https://aivoyage.vercel.app",
            "stack": ["Next.js", "Node.js", "AI APIs"],
            "resume_bullets": [
                "Built AI travel planner using LLM APIs",
                "Designed constraint-based system"
            ]
        },
        {
            "title": "AiVoya2 — AI Travel Planner",
            "live": "https://aivoyage.vercel.app",
            "stack": ["Next.js", "Node.js", "AI APIs"],
            "resume_bullets": [
                "Built AI travel planner using LLM APIs",
                "Designed constraint-based system"
            ]
        }
    ]


def dummy_insights():
    return [
        {
            "title": "BeanCraft — Coffee UI",
            "live": "https://beancraft.vercel.app",
            "description": "Premium coffee UI system"
        },
        {
            "title": "BeanCraft2 — Coffee UI",
            "live": "https://beancraft.vercel.app",
            "description": "Premium coffee UI system"
        }
    ]


# -------------------------
# ENDPOINT
# -------------------------
@router.post("/resume")
def test_resume():

    template = load_tex()

    result = generate_resume_pipeline(
        template,
        dummy_featured(),
        dummy_insights()
    )

    return result