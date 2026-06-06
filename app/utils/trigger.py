def should_trigger(commit_message: str) -> bool:
    if not commit_message:
        return False
    return True