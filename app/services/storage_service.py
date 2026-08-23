"""Generic Supabase Storage helper for artifact media (LinkedIn images, etc).
Résumé PDFs use their own bucket/versioning logic in resume_service."""
from __future__ import annotations

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase

logger = get_logger("storage_service")
MEDIA_BUCKET = "devsync-media"


def ensure_bucket() -> None:
    try:
        get_supabase().storage.create_bucket(MEDIA_BUCKET, options={"public": True})
    except Exception:
        pass


def upload_bytes(path: str, data: bytes, content_type: str) -> str:
    ensure_bucket()
    try:
        get_supabase().storage.from_(MEDIA_BUCKET).upload(path, data, {"content-type": content_type, "upsert": "true"})
        return get_supabase().storage.from_(MEDIA_BUCKET).get_public_url(path)
    except Exception as e:
        log_error(logger, "media upload failed", exc=e, service="supabase_storage", operation="upload_bytes", path=path)
        raise ExternalServiceError("supabase_storage", "upload_bytes", str(e), original=e) from e
