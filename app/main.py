from fastapi import FastAPI
from app.routes.github import router as github_router


app = FastAPI()

app.include_router(github_router, prefix="/github")


@app.get("/")
def health():
    return {"status": "running"}