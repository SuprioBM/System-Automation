"""RAG over Supabase pgvector. Supabase relational tables (projects,
artifacts, ...) remain the canonical source of truth; knowledge_chunks is a
derived retrieval index rebuilt from that data, never treated as authoritative
on its own. Retrieval is always scoped to `owner` (the portfolio's GitHub
user) so a multi-tenant deployment can't leak another user's data.
"""
from __future__ import annotations

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger, log_error
from app.core.supabase import get_supabase
from app.services.embeddings import embed_text

logger = get_logger("knowledge_service")


def index_project(owner: str, project_id: str | None, source: str, content: str, metadata: dict | None = None) -> None:
    if not content or not content.strip():
        return
    try:
        vector = embed_text(content)
        get_supabase().table("knowledge_chunks").insert({
            "owner": owner,
            "project_id": project_id,
            "source": source,
            "content": content,
            "embedding": vector,
            "metadata": metadata or {},
        }).execute()
    except Exception as e:
        log_error(logger, "failed to index knowledge chunk", exc=e, service="supabase",
                  operation="index_project", owner=owner, source=source)
        raise ExternalServiceError("supabase", "index_project", str(e), original=e) from e


def retrieve(owner: str, query: str, top_k: int = 8) -> list[dict]:
    try:
        vector = embed_text(query)
        res = get_supabase().rpc(
            "match_knowledge_chunks",
            {"query_embedding": vector, "match_owner": owner, "match_count": top_k},
        ).execute()
        return res.data or []
    except Exception as e:
        log_error(logger, "retrieval failed", exc=e, service="supabase", operation="retrieve", owner=owner)
        raise ExternalServiceError("supabase", "retrieve", str(e), original=e) from e
