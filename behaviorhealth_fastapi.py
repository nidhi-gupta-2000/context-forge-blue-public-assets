from fastapi import FastAPI
import requests

app = FastAPI()

SOURCE_URL = "https://assets.bcbsnc.com/assets/employer/content/healthandwellness/endpoints/behaviourHealth.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bcbsnc.com",
    "Origin": "https://www.bcbsnc.com"
}

@app.get("/behavior-health")
def get_behavior_health():
    response = requests.get(SOURCE_URL, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    # ✅ Just return directly — FastAPI handles serialization
    if isinstance(data, list):
        return data
    else:
        return [data]