def extract_commit_message(payload: dict) -> str:
    try:
        commit = payload["head_commit"]["message"]
        if commit != "publish:true":
            return ""
        return True
    except:
        return ""