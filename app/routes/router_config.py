from app.routes.discord_router import router as discord_router
from app.routes.github import router as github_router
from app.routes.health import router as health_router
from app.routes.linkedin import router as linkedin_router
from app.routes.portfolio import router as portfolio_router
from app.routes.resume import router as resume_router
from app.routes.workflows import router as workflows_router


def register_routers(app):
    app.include_router(github_router, prefix="/github")
    app.include_router(discord_router)
    app.include_router(portfolio_router)
    app.include_router(resume_router)
    app.include_router(linkedin_router)
    app.include_router(workflows_router)
    app.include_router(health_router)
