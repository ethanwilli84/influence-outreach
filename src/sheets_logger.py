import os
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = "ethan-admin"
CAMPAIGN = "influence-outreach"

def get_col():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]["outreach_records"]

def get_already_contacted() -> list:
    try:
        col = get_col()
        return [r["name"] for r in col.find({"campaign": CAMPAIGN}, {"name": 1}) if r.get("name")]
    except Exception as e:
        print(f"MongoDB read error: {e}")
        return []

def log_to_sheet(opportunity: dict, emails_sent: list, status: str = "Sent"):
    try:
        col = get_col()
        col.insert_one({
            "campaign": CAMPAIGN,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "name": opportunity.get("name", ""),
            "category": opportunity.get("category", ""),
            "website": opportunity.get("website", ""),
            "emailsSent": ", ".join(emails_sent) if emails_sent else "",
            "status": status,
            "description": opportunity.get("description", ""),
            "why_fit": opportunity.get("why_fit", ""),
            "createdAt": datetime.utcnow(),
        })
    except Exception as e:
        print(f"MongoDB log error: {e}")
