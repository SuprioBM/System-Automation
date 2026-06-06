def extract_repo_name(payload: dict) -> str:
    try:
        return payload["repository"]["name"]
    except:
        return ""