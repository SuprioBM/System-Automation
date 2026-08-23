"""Shared retry policy for external-service calls.

One place defining "retry according to policy" (spec §25/§28): bounded
attempts, exponential backoff, and every retry logged with a retry number so
it's visible in terminal output -- never a silent infinite loop, never a
silently swallowed failure.
"""
from __future__ import annotations

import functools
from typing import Callable, Type

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger

logger = get_logger("retry")


def _log_retry(service: str, operation: str):
    def _log(retry_state: RetryCallState) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(
            f"retrying {service}.{operation}",
            extra={
                "ctx": {
                    "service": service,
                    "operation": operation,
                    "retry_number": retry_state.attempt_number,
                    "error": str(exc) if exc else None,
                }
            },
        )

    return _log


def with_retries(
    service: str,
    operation: str,
    *,
    exceptions: tuple[Type[BaseException], ...],
    attempts: int = 3,
):
    """Decorator factory: retries `exceptions` up to `attempts` times with
    exponential backoff, logging every retry with `service`/`operation`/
    `retry_number`."""

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            retrying = retry(
                reraise=True,
                stop=stop_after_attempt(attempts),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
                retry=retry_if_exception_type(exceptions),
                before_sleep=_log_retry(service, operation),
            )
            return retrying(fn)(*args, **kwargs)

        return wrapper

    return decorator
