from fastapi import FastAPI
from app.routes.github import router as github_router
from app.routes.test import router as test_resume


app = FastAPI()

app.include_router(github_router, prefix="/github")
app.include_router(test_resume)


@app.get("/")
def health():
    return {"status": "running"}