"""GitHub App adapter: JWT app auth, installation tokens, webhook signature
verification, and repository/README/commit reads. This is the primary
GitHub integration per the locked architecture -- GITHUB_TOKEN (a personal
access token) is only used as a best-effort fallback if App auth is
unavailable, and every path that uses it says so in its logs.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from datetime import datetime, timezone

import jwt
import requests

from app.core.config import require, settings
from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.retry import with_retries

logger = get_logger("github_app")

GITHUB_API = "https://api.github.com"
_RETRYABLE = (requests.ConnectionError, requests.Timeout)

# In-memory installation-token cache: installation_id -> (token, expires_at_epoch)
_token_cache: dict[int, tuple[str, float]] = {}

FINAL_COMMIT_PATTERN = re.compile(
    r"^\s*devsync-publish\s*:\s*true\s*$|\[devsync:publish\]", re.IGNORECASE | re.MULTILINE
)


def verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Verify X-Hub-Signature-256 using GITHUB_WEBHOOK_SECRET. Returns False
    (never raises) on any mismatch or missing header -- callers must reject
    the request with 401, they must not process the payload either way."""
    secret = require("GITHUB_WEBHOOK_SECRET")
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def is_final_commit(commit_message: str) -> bool:
    """The special final-commit convention: a `DevSync-Publish: true` trailer
    line, or the shorthand `[devsync:publish]` token anywhere in the message."""
    if not commit_message:
        return False
    return bool(FINAL_COMMIT_PATTERN.search(commit_message))


def _app_jwt() -> str:
    app_id = require("GITHUB_APP_ID")
    private_key = require("GITHUB_PRIVATE_KEY")
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id}
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as e:
        raise ConfigurationError(f"GITHUB_PRIVATE_KEY is not a valid RSA key: {e}") from e


@with_retries("github", "get_installation_token", exceptions=_RETRYABLE)
def get_installation_token(installation_id: int) -> str:
    cached = _token_cache.get(installation_id)
    if cached and cached[1] - 30 > time.time():
        return cached[0]

    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json"}
    res = requests.post(url, headers=headers, timeout=15)
    if res.status_code >= 300:
        raise ExternalServiceError(
            "github", "get_installation_token", res.text, status_code=res.status_code
        )
    data = res.json()
    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")).timestamp()
    _token_cache[installation_id] = (data["token"], expires_at)
    return data["token"]


def _auth_headers(installation_id: int | None) -> dict:
    if installation_id is not None:
        try:
            token = get_installation_token(installation_id)
            return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        except (ConfigurationError, ExternalServiceError) as e:
            log_error(logger, "GitHub App auth failed, falling back to GITHUB_TOKEN if set",
                      exc=e, service="github", operation="get_installation_token")
    if settings.GITHUB_TOKEN:
        return {"Authorization": f"token {settings.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    raise ConfigurationError(
        "No usable GitHub credentials: installation token could not be minted and "
        "GITHUB_TOKEN is not set."
    )


@with_retries("github", "get_repo_details", exceptions=_RETRYABLE)
def get_repo_details(owner: str, repo: str, installation_id: int | None = None) -> dict:
    headers = _auth_headers(installation_id)
    res = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers, timeout=15)
    if res.status_code != 200:
        raise ExternalServiceError("github", "get_repo_details", res.text, status_code=res.status_code)
    return res.json()


@with_retries("github", "get_repo_readme", exceptions=_RETRYABLE)
def get_repo_readme(owner: str, repo: str, installation_id: int | None = None) -> str:
    """README content as plain text, or "" if the repo has none. A missing
    README is a normal case, not an error."""
    headers = dict(_auth_headers(installation_id))
    headers["Accept"] = "application/vnd.github.raw+json"
    res = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/readme", headers=headers, timeout=15)
    if res.status_code == 404:
        return ""
    if res.status_code != 200:
        raise ExternalServiceError("github", "get_repo_readme", res.text, status_code=res.status_code)
    return res.text
