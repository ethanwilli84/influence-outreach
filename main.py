import time
import json
import urllib.request
from datetime import datetime
from src.research import find_opportunities
from src.contact_finder import find_contacts
from src.emailer import send_email
from src.sheets_logger import log_to_sheet, get_already_contacted, get_config, ADMIN_URL, CAMPAIGN

def dedup_check(email: str, window_days: int = 90) -> dict:
    """Layer 1: Check central contacts DB (fast, campaign-based)."""
    try:
        payload = json.dumps({'action': 'check', 'email': email, 'dedupWindowDays': window_days}).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/contacts",
            data=payload, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Dedup DB check failed: {e}")
        return {'alreadyContacted': False}

def gmail_history_check(email: str, domain: str = None, name: str = None) -> dict:
    """Layer 2: Search actual Gmail for any prior contact — catches manual outreach outside campaigns."""
    try:
        payload = json.dumps({
            'email': email,
            'domain': domain or email.split('@')[1] if '@' in email else None,
            'name': name,
        }).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/gmail-check",
            data=payload, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Gmail history check failed: {e}, skipping gmail check")
        return {'shouldSkip': False, 'summary': {'sentCount': 0}}

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

def atomic_dedup(email: str, campaign_name: str = '', window_days: int = 90) -> dict:
    """Atomic check-and-record — prevents race condition between concurrent campaigns.
    
    If two campaigns run close together and both check the same email before
    either records it, both would send. This does the check + record in one
    atomic DB operation so only the first one wins.
    """
    try:
        payload = json.dumps({
            'action': 'check_and_record',
            'email': email,
            'channel': 'email',
            'campaign': CAMPAIGN,
            'platformName': campaign_name,
            'dedupWindowDays': window_days,
        }).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/contacts",
            data=payload, headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  Atomic dedup failed: {e}, using non-atomic fallback")
        return dedup_check(email, window_days)


def main():
    print(f"\n🚀 Starting outreach run — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    _gmail_cache: dict = {}  # domain -> {shouldSkip, sentCount} — avoid repeat Gmail searches per run

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

                # Layer 1: Atomic check-and-record (prevents race condition if 2 campaigns run close together)
                result = atomic_dedup(email, campaign_name=opp.get('name',''), window_days=config.get('dedupWindowDays', 90))
                if result.get('alreadyContacted'):
                    last = result.get('lastContact') or {}
                    race = ' (race caught)' if result.get('raceCaught') else ''
                    print(f"  ⏭ [DB] Skipping {email} — already contacted{race}")
                    continue

                # Layer 2: Deep Gmail history search
                # Searches sent mail + inbox — catches manual outreach outside campaigns
                domain = email.split('@')[1] if '@' in email else None
                # Cache by domain to avoid repeated IMAP searches for same company
                if domain and domain in _gmail_cache:
                    gmail_result = _gmail_cache[domain]
                else:
                    gmail_result = gmail_history_check(email, domain=domain, name=opp.get('name'))
                    if domain:
                        _gmail_cache[domain] = gmail_result

                if not gmail_result.get('ok') and gmail_result.get('shouldSkip'):
                    # Check failed — safe default is to skip
                    print(f"  ⏭ [Gmail] Skipping {email} — {gmail_result.get('verdict','check failed, skipping to be safe')}")
                    continue
                elif gmail_result.get('shouldSkip'):
                    sent = gmail_result.get('summary', {}).get('sentCount', 0)
                    history = gmail_result.get('sentHistory', [])
                    recent = history[0] if history else {}
                    print(f"  ⏭ [Gmail] Skipping {email}")
                    print(f"     Found {sent} prior sent email(s) to this domain")
                    if recent:
                        print(f"     Last: '{recent.get('subject','')}' on {recent.get('date','')} → {recent.get('to','')[:40]}")
                    continue
                else:
                    received = gmail_result.get('summary', {}).get('receivedCount', 0)
                    if received > 0:
                        print(f"  ⚠ [Gmail] They've emailed you {received}x but you haven't sent to them — proceeding")
                    else:
                        print(f"  ✓ [Gmail] No prior email history — clear to send")

                success = send_email(contact, opp, config=config)
                if success:
                    emails_sent.append(email)
                    print(f"  ✓ Sent to {email}")
                    # Contact already recorded atomically above via atomic_dedup
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
