def extract_commit_message(payload: dict) -> str:
    """Returns the actual HEAD commit message text (not a bool -- see
    ARCHITECTURE_REFERENCE.md §19.1 for the bug this replaces)."""
    try:
        return (payload.get("head_commit") or {}).get("message", "") or ""
    except (AttributeError, TypeError):
        return ""
