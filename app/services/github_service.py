from app.core.config import GITHUB_TOKEN, GITHUB_USERNAME
import requests



headers = {
    "Authorization": f"token {GITHUB_TOKEN}"
}


def get_repo_details(repo_name: str):
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}"
    res = requests.get(url, headers=headers)
    print(res)

    if res.status_code != 200:
        return {"error": "failed to fetch repo", "details": res.text}
    return res.json()