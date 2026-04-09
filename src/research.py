import anthropic
import json
import os
import re
import time
import urllib.request
import urllib.parse

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
ADMIN_URL = os.environ.get("ADMIN_URL", "https://ethan-admin-hlfdr.ondigitalocean.app")
CAMPAIGN = os.environ.get("CAMPAIGN_SLUG", "influence-outreach")

RESEARCH_PROMPT = """Search the web and find {per_session} NEW podcast shows or public speaking events that are a great fit for Ethan Williams (20yo NYC founder, $5M+ software company, The Taco Project community).

Target: actively booking guests, 1k-100k audience, entrepreneurship/gen z/fintech/lifestyle/sneakers focus.
Skip: mega-famous shows, pitch competitions, already-contacted platforms.

Already contacted (skip these): {already_contacted}

Search thoroughly, then provide your findings."""

EXTRACT_PROMPT = """Extract real companies/people from the research text below into a JSON array.

CRITICAL RULES:
- ONLY include entities that are explicitly mentioned in the research text
- NEVER invent, fabricate, or add "Placeholder" entries to meet a quota
- If only 3 real companies were found, return 3 items. Quality over quantity.
- Each entry must have a real name, real website, and real reason why they fit
- Skip any entity you're not 100% sure is real and verified in the research

Research findings:
{research_text}

Return a JSON array with ONLY verified, real entities found above. No markdown, no fences, just raw JSON:
[{{"name":"Real Company Name","category":"family_office","website":"https://verified-site.com","contact_page":"https://verified-site.com/contact","description":"What they actually do","why_fit":"Specific reason based on research"}}]"""


def get_from_lead_pool(already_contacted: list, limit: int = 30) -> list:
    """Pull leads from the pre-populated lead pool instead of researching from scratch.
    Falls back to empty list if pool is empty or unavailable.
    """
    try:
        url = f"{ADMIN_URL}/api/lead-pool?campaign={urllib.parse.quote(CAMPAIGN)}&status=pending&limit={limit}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        
        pool_leads = data.get("leads", [])
        if not pool_leads:
            return []
        
        # Filter out already contacted
        already_set = {name.lower() for name in already_contacted}
        filtered = [
            lead for lead in pool_leads
            if lead.get("name", "").lower() not in already_set
        ]
        
        print(f"  [LeadPool] {len(pool_leads)} in pool → {len(filtered)} not yet contacted")
        
        # Convert pool format to opportunity format
        opportunities = []
        for lead in filtered:
            opportunities.append({
                "name": lead["name"],
                "category": lead.get("category", "unknown"),
                "website": lead.get("website", ""),
                "contact_page": lead.get("contactPage") or lead.get("website", ""),
                "description": lead.get("description", ""),
                "why_fit": f"Pre-qualified lead from {lead.get('source', 'database')}",
                "email": lead.get("email"),  # Pre-found email if available
                "_pool_id": str(lead.get("_id", "")),
            })
        
        return opportunities
    except Exception as e:
        print(f"  [LeadPool] Error fetching pool: {e} — falling back to web research")
        return []


def mark_pool_lead_contacted(name: str, website: str = None):
    """Mark a lead pool entry as contacted after sending."""
    try:
        payload = json.dumps({"name": name, "website": website, "status": "contacted", "contactedBy": CAMPAIGN}).encode()
        req = urllib.request.Request(
            f"{ADMIN_URL}/api/lead-pool",
            data=payload, headers={"Content-Type": "application/json"}, method="PATCH"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Non-critical


def find_opportunities(already_contacted: list, config: dict = None, retries: int = 3) -> list:
    cfg = config or {}
    research_prompt_template = cfg.get("researchPrompt", "")
    per_session = cfg.get("perSession", 15)

    # STEP 1: Try lead pool first — pre-populated, no Claude research needed
    use_pool = cfg.get("useLeadPool", True)
    if use_pool:
        pool_leads = get_from_lead_pool(already_contacted, limit=per_session * 3)
        if len(pool_leads) >= per_session:
            print(f"  [LeadPool] Using {len(pool_leads)} pool leads — skipping web research this batch")
            return pool_leads[:per_session * 2]  # Return extra so contact finder has room to dedup
        elif pool_leads:
            print(f"  [LeadPool] Only {len(pool_leads)} pool leads — supplementing with web research")
        else:
            print(f"  [LeadPool] Pool empty — using web research")

    # STEP 2: Web research (fallback or supplement)
    already_list = [str(x)[:40] for x in already_contacted]
    if len(already_list) > 100:
        already_str = f"{len(already_list)} companies already contacted (recent: " + ", ".join(already_list[-40:]) + ")"
    else:
        already_str = ", ".join(already_list) if already_list else "none"

    for attempt in range(retries):
        try:
            research_q = (research_prompt_template or RESEARCH_PROMPT).replace(
                "{already_contacted}", already_str
            ).replace("{per_session}", str(per_session)) + """

CRITICAL RULES:
- Run web_search at least 4 times with DIFFERENT angles — vary by niche, geography, audience size, platform type
- DO NOT repeat any company from the already-contacted list above — that is a hard skip
- Prioritize OBSCURE and NICHE targets over well-known ones (they have less competition in their inbox)
- Report ONLY what you actually found with verified real URLs
- If you can only verify 5 real ones after searching, return 5 — quality beats quota
- NEVER invent Placeholder entries under any circumstances
- Each search must use DIFFERENT keywords than previous searches in this session"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": research_q}]
            )

            # Collect all text
            research_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    research_text += block.text + "\n"

            print(f"Research response length: {len(research_text)} chars")
            if len(research_text) < 200:
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return []

            # Step 2b: Extract structured data
            extract_response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": EXTRACT_PROMPT.replace("{research_text}", research_text[:6000])
                }]
            )

            extract_text = ""
            for block in extract_response.content:
                if hasattr(block, "text"):
                    extract_text += block.text

            print(f"Extract response length: {len(extract_text)} chars, preview: {extract_text[:80]}")

            # Clean and parse JSON
            clean = extract_text.strip()
            clean = re.sub(r'^```json\s*', '', clean)
            clean = re.sub(r'\s*```$', '', clean)
            clean = clean.strip()

            if not clean.startswith('['):
                idx = clean.find('[')
                if idx >= 0:
                    clean = clean[idx:]

            opportunities = json.loads(clean)

            # Validate and filter
            valid = []
            for opp in opportunities:
                name = opp.get("name", "").strip()
                if not name or "placeholder" in name.lower():
                    continue
                if name.lower() in {a.lower() for a in already_contacted}:
                    continue
                valid.append(opp)

            print(f"Found {len(valid)} real opportunities (extract step)")

            # Combine with any pool leads
            if 'pool_leads' in dir() and pool_leads:
                pool_names = {l['name'].lower() for l in pool_leads}
                web_only = [v for v in valid if v['name'].lower() not in pool_names]
                combined = pool_leads + web_only
                print(f"Combined: {len(pool_leads)} pool + {len(web_only)} web = {len(combined)} total")
                return combined

            return valid

        except json.JSONDecodeError as e:
            print(f"JSON parse error (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(3)
        except Exception as e:
            print(f"Research error (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                time.sleep(5)

    return []
