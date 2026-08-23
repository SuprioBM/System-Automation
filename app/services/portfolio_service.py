"""Triggers a rebuild/revalidation of the live portfolio site after an
approved change (new project, activated résumé) is persisted."""
from __future__ import annotations

import requests

from app.core.config import require
from app.core.errors import ExternalServiceError
from app.core.retry import with_retries


@with_retries("portfolio_site", "revalidate", exceptions=(requests.ConnectionError, requests.Timeout))
def trigger_revalidate() -> None:
    url = require("PORTFOLIO_REVALIDATE_URL")
    secret = require("REVALIDATE_SECRET")
    res = requests.post(url, headers={"x-secret": secret}, timeout=15)
    if res.status_code >= 300:
        raise ExternalServiceError("portfolio_site", "revalidate", res.text, status_code=res.status_code)
