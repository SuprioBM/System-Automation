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
    """decode_responses is deliberately NOT set: RQ stores pickled (binary)
    job payloads in Redis, and force-decoding every response as UTF-8
    corrupts that binary data (UnicodeDecodeError on dequeue). Callers that
    want strings (e.g. a raw GET/SET) should .decode() explicitly."""
    global _client
    if _client is None:
        url = require("REDIS_URL")
        _client = redis.from_url(url, socket_connect_timeout=5, socket_timeout=10)
    return _client


def ping() -> bool:
    try:
        return get_redis().ping()
    except redis.RedisError as e:
        raise ExternalServiceError("redis", "ping", str(e), original=e) from e


def get_queue(name: str = WORKFLOW_QUEUE_NAME) -> Queue:
    return Queue(name, connection=get_redis())
