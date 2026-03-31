import os
import json
import urllib.request
from datetime import datetime

ADMIN_URL = os.environ.get("ADMIN_URL", "https://ethan-admin-hlfdr.ondigitalocean.app")
CAMPAIGN = os.environ.get("CAMPAIGN_SLUG", "influence-outreach")

def _fetch(path: str) -> dict:
    try:
        req = urllib.request.Request(f"{ADMIN_URL}{path}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"API fetch error ({path}): {e}")
        return {}

def get_config() -> dict:
    """Fetch full campaign config from admin API."""
    return _fetch(f"/api/settings?campaign={CAMPAIGN}")

def get_already_contacted() -> list:
    try:
        records = _fetch(f"/api/outreach?campaign={CAMPAIGN}")
        return [r["name"] for r in records if r.get("name")]
    except Exception as e:
        print(f"API read error: {e}")
        return []

def log_to_sheet(opportunity: dict, emails_sent: list, status: str = "Sent"):
    try:
        payload = json.dumps({
            "campaign": CAMPAIGN,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "name": opportunity.get("name", ""),
            "category": opportunity.get("category", ""),
            "website": opportunity.get("website", ""),
            "emailsSent": ", ".join(emails_sent) if emails_sent else "",
            "status": status,
            "description": opportunity.get("description", ""),
            "why_fit": opportunity.get("why_fit", ""),
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/log",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                print(f"  Logged to DB: {opportunity.get('name', '')}")
    except Exception as e:
        print(f"  Log error: {e}")
