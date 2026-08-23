"""Defenses against prompt injection originating from repository content
(README, source, comments, commit messages). Repository content is always
untrusted input -- it is quoted into prompts inside clearly delimited,
labeled blocks and stripped of common injection phrasing, and the system
prompt for every node that consumes it explicitly instructs the model to
treat it as data, never as instructions.
"""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"ignore (all|previous|prior|above) instructions",
    r"disregard (all|previous|prior|above)",
    r"you are now",
    r"system prompt",
    r"new instructions?:",
    r"act as (?!an? (developer|engineer))",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Kept small deliberately: this Groq account has an 8000 tokens-per-minute
# cap on the configured model, which is a hard per-request ceiling too (a
# single request asking for more than that can never fit, regardless of
# pacing). A large README easily blows that budget once combined with the
# system prompt and reserved output tokens.
MAX_UNTRUSTED_CHARS = 2_500


def sanitize_untrusted(text: str | None, *, max_chars: int = MAX_UNTRUSTED_CHARS) -> str:
    if not text:
        return ""
    text = text[:max_chars]
    for pattern in _COMPILED:
        text = pattern.sub("[redacted: potential instruction]", text)
    return text


def wrap_untrusted_block(label: str, text: str | None) -> str:
    """Wrap repository-sourced content in an explicit, labeled, fenced block
    so the model can distinguish it from actual instructions."""
    body = sanitize_untrusted(text)
    return f"<untrusted_repository_{label}>\n{body}\n</untrusted_repository_{label}>"
