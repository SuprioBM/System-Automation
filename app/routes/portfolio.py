import requests
from app.core.config import REVALIDATE_SECRET

def trigger_revalidate():
    url = "https://supriobiswas.me/api/revalidate"

    headers = {
        "x-secret": REVALIDATE_SECRET
    }

    requests.post(url, headers=headers)