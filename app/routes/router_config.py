from app.routes.github import router as github_router
from app.routes.test import router as test_resume
from app.routes.discord_router import router as discord_router


def register_routers(app):
    app.include_router(github_router, prefix="/github")
    app.include_router(test_resume)
    app.include_router(discord_router)