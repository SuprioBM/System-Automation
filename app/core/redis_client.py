from __future__ import annotations

import redis
from rq import Queue

from app.core.config import require
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger

logger = get_logger("redis")

_client: redis.Redis | None = None

WORKFLOW_QUEUE_NAME = "devsync-workflows"


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        url = require("REDIS_URL")
        _client = redis.from_url(url, decode_responses=True, socket_connect_timeout=5, socket_timeout=10)
    return _client


def ping() -> bool:
    try:
        return get_redis().ping()
    except redis.RedisError as e:
        raise ExternalServiceError("redis", "ping", str(e), original=e) from e


def get_queue(name: str = WORKFLOW_QUEUE_NAME) -> Queue:
    return Queue(name, connection=get_redis())
