"""LinkedIn OAuth + publishing adapter. Never auto-publishes -- callers only
ever invoke publish_post() from the graph's publish node, after Discord
approval. If LINKEDIN_ACCESS_TOKEN isn't set yet, every call fails loudly
(ConfigurationError) rather than pretending to succeed.
"""
from __future__ import annotations

import requests

from app.core.config import require, settings
from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.retry import with_retries

API = "https://api.linkedin.com/v2"
_RETRYABLE = (requests.ConnectionError, requests.Timeout)


def get_authorize_url(state: str) -> str:
    client_id = require("LINKEDIN_CLIENT_ID")
    redirect_uri = require("LINKEDIN_REDIRECT_URI")
    scope = "openid profile w_member_social"
    return (
        "https://www.linkedin.com/oauth/v2/authorization"
        f"?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
        f"&scope={scope.replace(' ', '%20')}&state={state}"
    )


@with_retries("linkedin", "exchange_code", exceptions=_RETRYABLE)
def exchange_code_for_token(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": require("LINKEDIN_REDIRECT_URI"),
        "client_id": require("LINKEDIN_CLIENT_ID"),
        "client_secret": require("LINKEDIN_CLIENT_SECRET"),
    }
    res = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=data, timeout=15)
    if res.status_code != 200:
        raise ExternalServiceError("linkedin", "exchange_code", res.text, status_code=res.status_code)
    return res.json()


@with_retries("linkedin", "get_person_urn", exceptions=_RETRYABLE)
def get_person_urn(access_token: str) -> str:
    res = requests.get(f"{API}/userinfo", headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    if res.status_code != 200:
        raise ExternalServiceError("linkedin", "get_person_urn", res.text, status_code=res.status_code)
    return f"urn:li:person:{res.json()['sub']}"


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {require('LINKEDIN_ACCESS_TOKEN')}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


@with_retries("linkedin", "upload_image", exceptions=_RETRYABLE)
def _upload_image(person_urn: str, image_bytes: bytes) -> str:
    register = requests.post(
        f"{API}/assets?action=registerUpload",
        headers=_auth_headers(),
        json={
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": person_urn,
                "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
            }
        },
        timeout=15,
    )
    if register.status_code != 200:
        raise ExternalServiceError("linkedin", "register_upload", register.text, status_code=register.status_code)
    value = register.json()["value"]
    upload_url = value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset_urn = value["asset"]

    upload = requests.put(upload_url, data=image_bytes,
                           headers={"Authorization": f"Bearer {require('LINKEDIN_ACCESS_TOKEN')}"}, timeout=30)
    if upload.status_code not in (200, 201):
        raise ExternalServiceError("linkedin", "upload_image_binary", upload.text, status_code=upload.status_code)
    return asset_urn


@with_retries("linkedin", "publish_post", exceptions=_RETRYABLE)
def publish_post(text: str, image_bytes: bytes | None = None) -> dict:
    person_urn = settings.LINKEDIN_PERSON_URN or get_person_urn(require("LINKEDIN_ACCESS_TOKEN"))

    media = []
    if image_bytes:
        asset_urn = _upload_image(person_urn, image_bytes)
        media = [{"status": "READY", "media": asset_urn}]

    body = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE" if media else "NONE",
                **({"media": media} if media else {}),
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    res = requests.post(f"{API}/ugcPosts", headers=_auth_headers(), json=body, timeout=20)
    if res.status_code not in (200, 201):
        raise ExternalServiceError("linkedin", "publish_post", res.text, status_code=res.status_code)
    post_id = res.headers.get("x-restli-id") or res.json().get("id")
    return {"post_id": post_id}
