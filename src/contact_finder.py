import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DEFAULT_PROMPT = """Find contact email addresses for "{name}" ({website}).

Search their website to find:
1. Emails on their contact/booking/apply page: {contact_page}
2. The producer, booking manager, or guest coordinator
3. Common patterns: contact@, booking@, press@, apply@, hello@, guests@, [firstname]@domain.com

Return ONLY a valid JSON array. Max 4 contacts. No other text:
[{{"email": "email@domain.com", "name": "First Last or null", "role": "host/producer/booking/general", "confidence": "high/medium/low"}}]

Only include emails you actually found or can reasonably guess from their domain pattern."""

def find_contacts(opportunity: dict, config: dict = None, retries: int = 3) -> list:
    cfg = config or {}
    prompt_template = cfg.get("contactPrompt", DEFAULT_PROMPT)
    max_contacts = cfg.get("maxContactsPerPlatform", 3)
    skip_low = cfg.get("skipLowConfidence", True)

    # Use simple string replace instead of .format() to avoid KeyError on JSON curly braces in template
    prompt = prompt_template.replace("{name}", opportunity.get("name", ""))                              .replace("{website}", opportunity.get("website", ""))                              .replace("{contact_page}", opportunity.get("contact_page", opportunity.get("website", "")))

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            contacts = parse_json(full_text)

            if skip_low:
                filtered = [c for c in contacts if c.get("confidence") != "low"]
                contacts = filtered if filtered else contacts

            if not contacts:
                print(f"  No verified contacts found, trying guessed emails...")
                return guess_fallback_emails(opportunity, config)

            # Pad with guessed emails if verified contacts < max_contacts
            verified = contacts[:max_contacts]
            if len(verified) < max_contacts and cfg.get('useFallbackEmails', True):
                still_need = max_contacts - len(verified)
                guessed = guess_fallback_emails(opportunity, config)
                # Exclude domains already covered by verified contacts
                verified_domains = {e.get('email','').split('@')[1] for e in verified if '@' in e.get('email','')}
                guessed = [g for g in guessed if g['email'].split('@')[1] not in verified_domains]
                if guessed:
                    print(f"  Found {len(verified)} verified, padding with {min(still_need, len(guessed))} guessed email(s)")
                    verified = verified + guessed[:still_need]
            return verified

        except anthropic.RateLimitError as e:
            wait = 30 * (attempt + 1)
            print(f"  Rate limit hit, waiting {wait}s before retry {attempt + 1}/{retries}...")
            time.sleep(wait)
        except Exception as e:
            print(f"  Contact finder error: {e}")
            break

    print(f"  Failed after {retries} retries, trying guessed emails...")
    return guess_fallback_emails(opportunity, config)

def guess_fallback_emails(opportunity: dict, config: dict = None) -> list:
    """Generate guessed email addresses when no verified contacts found.
    Uses prefixes configured per-campaign in admin settings.
    Falls back to sensible defaults if not configured.
    """
    cfg = config or {}
    
    # Respect campaign-level toggle
    if not cfg.get("useFallbackEmails", True):
        return []

    website = opportunity.get("website", "")
    name = opportunity.get("name", "")
    category = opportunity.get("category", "").lower()

    if not website:
        return []

    # Extract clean domain
    import re
    domain_match = re.search(r'(?:https?://)?(?:www\.)?([^/\s]+)', website)
    if not domain_match:
        return []
    domain = domain_match.group(1).lower().strip()

    # Use campaign-configured prefixes if set, otherwise smart defaults by category
    configured = cfg.get("fallbackPrefixes", [])
    if configured:
        prefixes = configured
    else:
        # Smart defaults by category
        prefixes = ["info", "contact", "hello"]
        if any(kw in category for kw in ["lend", "finance", "credit", "bank", "capital", "fund", "invest"]):
            prefixes += ["lending", "funding", "investors", "partnerships", "business", "commercial"]
        elif any(kw in category for kw in ["podcast", "media", "press", "publish"]):
            prefixes += ["press", "media", "podcast", "guest", "bookings", "pitch"]
        elif any(kw in category for kw in ["warehouse", "logistics", "supply"]):
            prefixes += ["partnerships", "business", "sales", "operations"]
        else:
            prefixes += ["partnerships", "business", "support"]

    emails = []
    for prefix in prefixes:
        emails.append({
            "email": f"{prefix}@{domain}",
            "name": f"{name} ({prefix}@)",
            "title": "General Contact (guessed)",
            "confidence": "low",
            "guessed": True,
        })

    return emails[:6]  # Max 6 fallback guesses


def parse_json(text: str) -> list:
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            if part.startswith("json"):
                text = part[4:].strip(); break
            elif "[" in part:
                text = part.strip(); break
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try: return json.loads(match.group())
            except: pass
    return []
