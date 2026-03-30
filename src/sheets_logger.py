import gspread
import json
import os
from datetime import datetime
from google.oauth2.service_account import Credentials

SHEET_ID = "1woOQZ6hpN8uDATFZar0Nm7QVwMDsWM7adQpl1nxGse0"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
HEADERS = ['Date', 'Platform Name', 'Category', 'Website', 'Emails Sent', 'Status', 'Description', 'Why Fit']

def get_client():
    creds = Credentials.from_service_account_info(json.loads(os.environ["GOOGLE_SHEETS_CREDS"]), scopes=SCOPES)
    return gspread.authorize(creds)

def get_already_contacted() -> list:
    try:
        sheet = get_client().open_by_key(SHEET_ID).sheet1
        return [r['Platform Name'] for r in sheet.get_all_records() if r.get('Platform Name')]
    except Exception as e:
        print(f"Sheet read error: {e}")
        return []

def log_to_sheet(opportunity: dict, emails_sent: list, status: str = 'Sent'):
    try:
        sheet = get_client().open_by_key(SHEET_ID).sheet1
        if not sheet.get_all_records():
            sheet.insert_row(HEADERS, 1)
        sheet.append_row([
            datetime.now().strftime('%Y-%m-%d'),
            opportunity.get('name', ''),
            opportunity.get('category', ''),
            opportunity.get('website', ''),
            ', '.join(emails_sent) if emails_sent else '',
            status,
            opportunity.get('description', ''),
            opportunity.get('why_fit', '')
        ])
    except Exception as e:
        print(f"Sheet log error: {e}")
