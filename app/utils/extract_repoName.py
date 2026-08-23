def extract_repo_name(payload: dict) -> str:
    """Returns the full "owner/repo" name, required for GitHub App API calls."""
    try:
        return (payload.get("repository") or {}).get("full_name", "") or ""
    except (AttributeError, TypeError):
        return ""
