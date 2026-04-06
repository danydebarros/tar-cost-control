"""
Forecast persistence: auto-save/load via GitHub repo.
Stores forecast snapshots as JSON files in the repo's data/ folder.
"""

import json
import base64
import requests
import streamlit as st
from datetime import datetime

REPO = "danydebarros/tar-cost-control"
FORECAST_PATH = "data/forecast_latest.json"
BRANCH = "main"

# Token stored in Streamlit secrets or hardcoded for now
def _get_token():
    """Get GitHub token from Streamlit secrets or environment."""
    try:
        return st.secrets["GITHUB_TOKEN"]
    except Exception:
        return None


def _headers():
    token = _get_token()
    if not token:
        return {}
    return {"Authorization": f"token {token}"}


def save_forecast(plans: dict, saved_by: str, note: str = "",
                  params: dict = None) -> bool:
    """Save forecast to GitHub repo as data/forecast_latest.json.
    Also keeps a timestamped backup."""
    token = _get_token()
    if not token:
        st.error(
            "GitHub token not configured. Add GITHUB_TOKEN to Streamlit secrets "
            "to enable online forecast saving."
        )
        return False

    params = params or {}
    snapshot = {
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "saved_by": saved_by,
        "note": note,
        "hours_per_day": params.get("hours_per_day", 10),
        "nt_pct": params.get("nt_pct", 75),
        "forecast_days": params.get("forecast_days", 14),
        "plans": plans,
    }

    content = json.dumps(snapshot, indent=2, default=str)
    encoded = base64.b64encode(content.encode()).decode()

    # Check if file exists (need SHA to update)
    sha = _get_file_sha(FORECAST_PATH)

    payload = {
        "message": f"Forecast saved by {saved_by} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{FORECAST_PATH}",
        json=payload,
        headers=_headers(),
        timeout=15,
    )

    if resp.status_code in (200, 201):
        return True
    else:
        st.error(f"Failed to save forecast: {resp.status_code} - {resp.text[:200]}")
        return False


def load_forecast() -> dict:
    """Load the latest forecast from GitHub repo."""
    token = _get_token()
    if not token:
        return {}

    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{FORECAST_PATH}",
        headers=_headers(),
        timeout=10,
    )

    if resp.status_code != 200:
        return {}

    try:
        content = base64.b64decode(resp.json()["content"]).decode()
        return json.loads(content)
    except Exception:
        return {}


def _get_file_sha(path: str) -> str:
    """Get the SHA of an existing file in the repo (needed for updates)."""
    resp = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{path}",
        headers=_headers(),
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None
