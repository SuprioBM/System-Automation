from fastapi import FastAPI
from app.routes.router_config import register_routers

app = FastAPI()


register_routers(app)

@app.get("/")
def health():
    return {"status": "running"}