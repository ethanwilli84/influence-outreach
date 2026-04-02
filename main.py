import time
from datetime import datetime
from src.research import find_opportunities
from src.contact_finder import find_contacts
from src.emailer import send_email
from src.sheets_logger import log_to_sheet, get_already_contacted, get_config

def main():
    print(f"\n🚀 Starting outreach run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Fetch campaign config from admin (research prompt, contact prompt, template, etc.)
    config = get_config()
    print(f"Config loaded: perSession={config.get('perSession', 15)}, emailSubject={config.get('emailSubject', 'default')}\n")

    already_contacted = get_already_contacted()
    print(f"Already contacted: {len(already_contacted)} platforms\n")

    opportunities = find_opportunities(already_contacted, config=config)
    print(f"Found {len(opportunities)} new opportunities\n")

    if not opportunities:
        print("No opportunities found, exiting.")
        return

    # Wait after research to reset rate limit window
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
                # Dedup check — don't email same person from different campaigns
                try:
                    import json as _json
                    import urllib.request as _req
                    dedup_payload = _json.dumps({'action':'check','email':email,'dedupWindowDays':90}).encode()
                    dedup_req = _req.Request(f"{ADMIN_URL}/api/contacts", data=dedup_payload, headers={'Content-Type':'application/json'}, method='POST')
                    with _req.urlopen(dedup_req, timeout=10) as r:
                        dedup = _json.loads(r.read())
                    if dedup.get('alreadyContacted'):
                        last = dedup.get('lastContact', {})
                        print(f"  ⏭ Skipping {email} — already contacted via {last.get('campaign')} ({last.get('date','')})")
                        continue
                except Exception as e:
                    print(f"  Dedup check failed: {e}, sending anyway")

                success = send_email(contact, opp, config=config)
                if success:
                    emails_sent.append(email)
                    print(f"  ✓ Sent to {email}")
                    # Record in central contacts DB
                    try:
                        record_payload = _json.dumps({'action':'record','email':email,'channel':'email','campaign':CAMPAIGN,'platformName':opp.get('name','')}).encode()
                        record_req = _req.Request(f"{ADMIN_URL}/api/contacts", data=record_payload, headers={'Content-Type':'application/json'}, method='POST')
                        with _req.urlopen(record_req, timeout=10) as r:
                            pass
                    except Exception as e:
                        print(f"  Contact record failed: {e}")
                time.sleep(3)

            if emails_sent:
                log_to_sheet(opp, emails_sent, status='Sent')
                sent_count += 1
            else:
                log_to_sheet(opp, [], status='Send Failed')

            print()
            time.sleep(15)

        except Exception as e:
            print(f"  ✗ Error: {e}\n")

    print(f"✅ Done. Successfully sent to {sent_count} platforms.")

if __name__ == "__main__":
    main()
