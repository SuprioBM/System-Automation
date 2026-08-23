"""Structured logging.

Emits one block per event with explicit key=value context lines (workflow_id,
run_id, node, repository, commit, service, operation, status, error type,
retry number) plus a preserved traceback on errors. Never swallows an
exception silently, never logs secret-shaped values.
"""
from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

_REDACT_KEY_MARKERS = ("token", "key", "secret", "password", "authorization", "private")


def _redact(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _REDACT_KEY_MARKERS) and value:
        return "***redacted***"
    return value


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx: dict = getattr(record, "ctx", {}) or {}
        lines = [f"[{record.levelname}]"]
        lines.append(f"timestamp={self.formatTime(record, datefmt='%Y-%m-%dT%H:%M:%S%z')}")
        lines.append(f"logger={record.name}")
        for k, v in ctx.items():
            if v is None:
                continue
            lines.append(f"{k}={_redact(k, v)}")
        lines.append(f"message={record.getMessage()}")
        if record.exc_info:
            lines.append("Traceback:")
            lines.append("".join(traceback.format_exception(*record.exc_info)))
        return "\n".join(lines)


_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    from app.core.config import settings

    # Windows consoles/redirected-file streams default to cp1252, which can't
    # encode most non-ASCII characters (em dashes, curly quotes, non-breaking
    # hyphens, emoji). That silently breaks logging.StreamHandler.emit() --
    # the record is dropped and only a "--- Logging error ---" stub is
    # printed, hiding the real message. Force UTF-8 on stdout if possible.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ContextFormatter())
    root = logging.getLogger("devsync")
    root.setLevel(getattr(logging, (settings.LOG_LEVEL or "INFO").upper(), logging.INFO))
    root.handlers = [handler]
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(f"devsync.{name}")


def log_event(logger: logging.Logger, level: int, message: str, **ctx) -> None:
    logger.log(level, message, extra={"ctx": ctx})


def log_error(logger: logging.Logger, message: str, *, exc: BaseException | None = None, **ctx) -> None:
    """Log an error, preserving the original traceback whenever `exc` is
    given. Pass exc=None for an expected/business-rule rejection that isn't
    an exception (e.g. an invalid signature) -- no traceback is printed."""
    logger.error(message, exc_info=exc if exc is not None else False, extra={"ctx": ctx})
