"""Typed error hierarchy used across services, routes, workers and graph nodes.

Differentiates expected business failures from external-service failures and
unexpected system exceptions, per DevSync's error-visibility requirements.
Every error carries enough structured context to be logged without needing
to re-derive it at the call site.
"""
from __future__ import annotations


class DevSyncError(Exception):
    """Base class for all DevSync-raised errors."""


class ConfigurationError(DevSyncError):
    """Required configuration is missing or invalid. Should stop startup / the
    specific operation, never be silently downgraded to a mock."""


class ValidationFailure(DevSyncError):
    """A business-rule / schema validation failed (e.g. artifact validation,
    RepoAnalysis shape). Expected, not a bug."""


class BusinessRejection(DevSyncError):
    """A deterministic application-logic decision rejected an action (e.g.
    scoring says REJECT, resume candidate not an improvement). Expected."""


class ExternalServiceError(DevSyncError):
    """A call to an external service (GitHub, Groq, Supabase, Discord,
    LinkedIn, Pollinations, LaTeX compiler) failed."""

    def __init__(
        self,
        service: str,
        operation: str,
        message: str,
        *,
        status_code: int | None = None,
        original: Exception | None = None,
    ):
        self.service = service
        self.operation = operation
        self.status_code = status_code
        self.original = original
        super().__init__(f"{service}.{operation} failed: {message}")


class IdempotencyConflict(DevSyncError):
    """The same event/delivery has already been processed."""


class StaleApprovalError(DevSyncError):
    """A Discord approval interaction referenced a workflow/artifact version
    that is no longer current."""


class RetryExhausted(DevSyncError):
    """A node/operation exhausted its retry budget."""

    def __init__(self, operation: str, attempts: int, last_error: Exception | None = None):
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"{operation} failed after {attempts} attempts")
