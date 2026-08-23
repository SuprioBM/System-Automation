"""Pollinations adapter for LinkedIn post image generation."""
from __future__ import annotations

import urllib.parse

import requests

from app.core.config import require, settings
from app.core.errors import ExternalServiceError
from app.core.retry import with_retries


@with_retries("pollinations", "generate_image", exceptions=(requests.ConnectionError, requests.Timeout))
def generate_image(prompt: str, *, width: int = 1024, height: int = 1024) -> bytes:
    base = require("POLLINATIONS_BASE_URL")
    encoded = urllib.parse.quote(prompt)
    params = {"width": width, "height": height, "nologo": "true"}
    if settings.POLLINATIONS_API_TOKEN:
        params["token"] = settings.POLLINATIONS_API_TOKEN
    url = f"{base}/prompt/{encoded}"
    res = requests.get(url, params=params, timeout=60)
    if res.status_code != 200 or not res.content:
        raise ExternalServiceError("pollinations", "generate_image", res.text[:500], status_code=res.status_code)
    return res.content
