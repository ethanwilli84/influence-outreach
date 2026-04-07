"""
run_all.py — Campaign orchestrator

Runs each campaign as a SEPARATE SUBPROCESS so environment variables
(especially CAMPAIGN_SLUG) are fully isolated per campaign.

The importlib.reload approach was broken: CAMPAIGN in sheets_logger.py
is set at module import time, so it never updated for campaigns 2, 3, 4.
All their records were logged under campaign #1 (influence-outreach).
"""

import os
import sys
import time
import json
import subprocess
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
    try:
        result = api("/api/campaign-lock", "POST", {
            "action": "acquire",
            "campaign": campaign_slug,
            "runnerPid": os.getpid(),
        })
        return result.get("acquired", False)
    except Exception as e:
        print(f"  Lock acquire failed: {e} — proceeding anyway")
        return True

def release_lock(campaign_slug: str):
    try:
        api("/api/campaign-lock", "POST", {"action": "release", "campaign": campaign_slug})
    except Exception as e:
        print(f"  Lock release failed: {e}")

def run_campaign(slug: str):
    """Run a single campaign as a subprocess — fully isolated env vars, fresh module state."""
    print(f"\n{'='*60}")
    print(f"  Running: {slug}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Copy current env and set campaign slug
    env = os.environ.copy()
    env["CAMPAIGN_SLUG"] = slug

    result = subprocess.run(
        [sys.executable, "main.py"],
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    if result.returncode != 0:
        print(f"\n⚠ Campaign {slug} exited with code {result.returncode}")

def main():
    print(f"\n🚀 Campaign Orchestrator starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    try:
        campaigns = api("/api/campaigns")
    except Exception as e:
        print(f"Failed to fetch campaigns: {e}")
        return

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

    if SPECIFIC_CAMPAIGN:
        active = [c for c in active if c["slug"] == SPECIFIC_CAMPAIGN]
        if not active:
            print(f"Campaign '{SPECIFIC_CAMPAIGN}' not found or paused")
            return

    print(f"\n📋 Running {len(active)} campaign(s) sequentially: {[c['slug'] for c in active]}\n")

    for i, campaign in enumerate(active):
        slug = campaign["slug"]

        if not acquire_lock(slug):
            print(f"  🔒 {slug} already locked — skipping")
            continue

        try:
            try:
                fresh_settings = api(f"/api/settings?campaign={slug}")
                if fresh_settings.get("paused"):
                    print(f"  ⏸ {slug} paused — skipping")
                    release_lock(slug)
                    continue
            except Exception as e:
                print(f"  Warning: couldn't re-check pause status: {e}")

            run_campaign(slug)
        except Exception as e:
            print(f"\n❌ Campaign {slug} failed: {e}")
        finally:
            release_lock(slug)

        if i < len(active) - 1:
            cooldown = 90
            print(f"\n⏳ Cooling down {cooldown}s before next campaign...\n")
            time.sleep(cooldown)

    print(f"\n✅ All campaigns complete — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

if __name__ == "__main__":
    main()
