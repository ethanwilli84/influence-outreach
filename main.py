import time
import json
import urllib.request
from datetime import datetime
from src.research import find_opportunities
from src.contact_finder import find_contacts
from src.emailer import send_email
from src.sheets_logger import log_to_sheet, get_already_contacted, get_config, ADMIN_URL, CAMPAIGN

def dedup_check(email: str, window_days: int = 90) -> dict:
    """Check if email was already contacted. Returns {alreadyContacted, lastContact}."""
    try:
        payload = json.dumps({'action': 'check', 'email': email, 'dedupWindowDays': window_days}).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/contacts",
            data=payload, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Dedup check failed: {e}, sending anyway")
        return {'alreadyContacted': False}

def record_contact(email: str, platform_name: str):
    """Record a sent email in the central contacts DB."""
    try:
        payload = json.dumps({
            'action': 'record', 'email': email, 'channel': 'email',
            'campaign': CAMPAIGN, 'platformName': platform_name
        }).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/contacts",
            data=payload, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception as e:
        print(f"  Contact record failed: {e}")

def main():
    print(f"\n🚀 Starting outreach run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    config = get_config()
    print(f"Config loaded: perSession={config.get('perSession', 15)}, emailSubject={config.get('emailSubject', 'default')}\n")

    already_contacted = get_already_contacted()
    print(f"Already contacted: {len(already_contacted)} platforms\n")

    opportunities = find_opportunities(already_contacted, config=config)
    print(f"Found {len(opportunities)} new opportunities\n")

    if not opportunities:
        print("No opportunities found, exiting.")
        return

    print("Waiting 65 seconds before contact search to avoid rate limits...\n")
    time.sleep(65)

    sent_count = 0
    for opp in opportunities:
        try:
            print(f"Processing: {opp.get('name')} ({opp.get('category')})")
            contacts = find_contacts(opp, config=config)

            if not contacts:
                print(f"  ✗ No contacts found, logging anyway\n")
                log_to_sheet(opp, [], status='No Contact Found')
                continue

            emails_sent = []
            for contact in contacts:
                email = (contact.get('email') or '').strip()
                if not email:
                    continue

                # Dedup — skip if already contacted within window
                result = dedup_check(email, window_days=config.get('dedupWindowDays', 90))
                if result.get('alreadyContacted'):
                    last = result.get('lastContact') or {}
                    print(f"  ⏭ Skipping {email} — already contacted via {last.get('campaign','?')} on {str(last.get('date','?'))[:10]}")
                    continue

                success = send_email(contact, opp, config=config)
                if success:
                    emails_sent.append(email)
                    print(f"  ✓ Sent to {email}")
                    record_contact(email, opp.get('name', ''))
                time.sleep(3)

            if emails_sent:
                log_to_sheet(opp, emails_sent, status='Sent')
                sent_count += 1
            elif contacts:
                log_to_sheet(opp, [], status='Send Failed')
            print()
            time.sleep(15)

        except Exception as e:
            print(f"  ✗ Error: {e}\n")

    print(f"✅ Done. Successfully sent to {sent_count} platforms.")

if __name__ == "__main__":
    main()
