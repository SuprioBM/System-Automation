"""Configurable embedding provider for RAG. Default is a local fastembed
model (no external API key required); swap EMBEDDING_PROVIDER/EMBEDDING_MODEL
in .env to point at a different provider without touching call sites.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings
from app.core.errors import ConfigurationError, ExternalServiceError


class EmbeddingProvider(ABC):
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider(EmbeddingProvider):
    dimension = 384  # BAAI/bge-small-en-v1.5

    def __init__(self, model_name: str):
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise ConfigurationError("fastembed is not installed (pip install -r requirements.txt)") from e
        try:
            self._model = TextEmbedding(model_name=model_name)
        except Exception as e:
            raise ExternalServiceError("fastembed", "load_model", str(e), original=e) from e

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return [vec.tolist() for vec in self._model.embed(texts)]
        except Exception as e:
            raise ExternalServiceError("fastembed", "embed", str(e), original=e) from e


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    provider = (settings.EMBEDDING_PROVIDER or "fastembed").lower()
    if provider == "fastembed":
        return FastEmbedProvider(settings.EMBEDDING_MODEL)
    raise ConfigurationError(f"Unknown EMBEDDING_PROVIDER: {provider}")


def embed_text(text: str) -> list[float]:
    return get_embedding_provider().embed([text])[0]
