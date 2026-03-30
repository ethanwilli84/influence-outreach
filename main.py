import time
from datetime import datetime
from src.research import find_opportunities
from src.contact_finder import find_contacts
from src.emailer import send_email
from src.sheets_logger import log_to_sheet, get_already_contacted

def main():
    print(f"\n🚀 Starting outreach run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    already_contacted = get_already_contacted()
    print(f"Already contacted: {len(already_contacted)} platforms\n")

    opportunities = find_opportunities(already_contacted)
    print(f"Found {len(opportunities)} new opportunities\n")

    if not opportunities:
        print("No opportunities found, exiting.")
        return

    # Wait after research call to reset rate limit window
    print("Waiting 65 seconds before contact search to avoid rate limits...\n")
    time.sleep(65)

    sent_count = 0
    for opp in opportunities:
        try:
            print(f"Processing: {opp.get('name')} ({opp.get('category')})")
            contacts = find_contacts(opp)

            if not contacts:
                print(f"  ✗ No contacts found, logging anyway\n")
                log_to_sheet(opp, [], status='No Contact Found')
                continue

            emails_sent = []
            for contact in contacts:
                success = send_email(contact, opp)
                if success:
                    emails_sent.append(contact.get('email'))
                    print(f"  ✓ Sent to {contact.get('email')}")
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
