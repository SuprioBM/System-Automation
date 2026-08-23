from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import REQUIRED_FOR_API, validate_settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.routes.router_config import register_routers

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        validate_settings(REQUIRED_FOR_API)
    except ConfigurationError as e:
        logger.error(f"startup aborted: {e}")
        raise
    logger.info("DevSync API starting")
    yield


app = FastAPI(title="DevSync", lifespan=lifespan)

register_routers(app)


@app.get("/")
def health():
    return {"status": "running"}
