def build_repo_context(repo_data: dict):
    return {
        k: v
        for k, v in {
            "name": repo_data.get("name"),
            "description": repo_data.get("description"),
            "language": repo_data.get("language"),
            "homepage": repo_data.get("homepage"),
            "topics": repo_data.get("topics"),
        }.items()
        if v not in [None, "", []]
    }