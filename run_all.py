"""
run_all.py — Campaign orchestrator

Fetches all active campaigns from the admin API and runs them sequentially
on a single GitHub Actions runner. This prevents:
  - Dedup race conditions (campaigns can't overlap)
  - Gmail rate limit hammering
  - Multiple IMAP connections fighting each other

Flow:
  1. Fetch all active, unpaused campaigns from admin
  2. For each campaign: acquire DB lock → run → release lock → wait 60s cooldown
  3. If a lock already exists (shouldn't happen in GH Actions but safety net) → skip
"""

import os
import time
import json
import urllib.request
from datetime import datetime

ADMIN_URL = os.environ.get("ADMIN_URL", "https://ethan-admin-hlfdr.ondigitalocean.app")
SPECIFIC_CAMPAIGN = os.environ.get("SPECIFIC_CAMPAIGN", "").strip()

def api(path: str, method: str = "GET", body: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(f"{ADMIN_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def acquire_lock(campaign_slug: str) -> bool:
    """Try to acquire a run lock. Returns False if already locked (another run in progress)."""
    try:
        result = api("/api/campaign-lock", "POST", {
            "action": "acquire",
            "campaign": campaign_slug,
            "runnerPid": os.getpid(),
        })
        return result.get("acquired", False)
    except Exception as e:
        print(f"  Lock acquire failed: {e} — proceeding anyway")
        return True  # Safe to proceed if lock system is down

def release_lock(campaign_slug: str):
    try:
        api("/api/campaign-lock", "POST", {"action": "release", "campaign": campaign_slug})
    except Exception as e:
        print(f"  Lock release failed: {e}")

def run_campaign(slug: str):
    """Run a single campaign by setting CAMPAIGN_SLUG and calling main.py logic."""
    os.environ["CAMPAIGN_SLUG"] = slug
    print(f"\n{'='*60}")
    print(f"  Running: {slug}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Import and run main inline (same process, no subprocess needed)
    # This shares the same Python environment and avoids process overhead
    import importlib
    import main as outreach_main
    importlib.reload(outreach_main)  # Reload so CAMPAIGN_SLUG env var is picked up fresh
    outreach_main.main()

def main():
    print(f"\n🚀 Campaign Orchestrator starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Fetch all campaigns
    try:
        campaigns = api("/api/campaigns")
    except Exception as e:
        print(f"Failed to fetch campaigns: {e}")
        return

    # Filter: only active + not paused
    active = []
    for c in campaigns:
        if not c.get("active", True):
            continue
        try:
            settings = api(f"/api/settings?campaign={c['slug']}")
            if settings.get("paused"):
                print(f"  ⏸ Skipping {c['slug']} — paused")
                continue
            active.append(c)
        except Exception as e:
            print(f"  ⚠ Couldn't fetch settings for {c['slug']}: {e}")

    # If a specific campaign was requested (manual dispatch), filter to just that one
    if SPECIFIC_CAMPAIGN:
        active = [c for c in active if c["slug"] == SPECIFIC_CAMPAIGN]
        if not active:
            print(f"Campaign '{SPECIFIC_CAMPAIGN}' not found or paused")
            return

    print(f"\n📋 Running {len(active)} campaign(s) sequentially: {[c['slug'] for c in active]}\n")

    for i, campaign in enumerate(active):
        slug = campaign["slug"]

        # Acquire lock
        if not acquire_lock(slug):
            print(f"  🔒 {slug} is already locked (another run in progress?) — skipping")
            continue

        try:
            # Re-check pause status right before running — user may have paused/unpaused since startup
            try:
                fresh_settings = api(f"/api/settings?campaign={slug}")
                if fresh_settings.get("paused"):
                    print(f"  ⏸ {slug} is paused (re-checked just before run) — skipping")
                    release_lock(slug)
                    continue
            except Exception as e:
                print(f"  Warning: couldn't re-check pause status: {e}")
            
            run_campaign(slug)
        except Exception as e:
            print(f"\n❌ Campaign {slug} failed: {e}")
        finally:
            release_lock(slug)

        # Cooldown between campaigns — let Gmail breathe + dedup writes to settle
        if i < len(active) - 1:
            cooldown = 90  # 90 seconds between campaigns
            print(f"\n⏳ Cooling down {cooldown}s before next campaign...\n")
            time.sleep(cooldown)

    print(f"\n✅ All campaigns complete — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

if __name__ == "__main__":
    main()
