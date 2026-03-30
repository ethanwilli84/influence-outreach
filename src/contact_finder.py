import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROMPT = """Find contact email addresses for "{name}" ({website}).

Search their website to find:
1. Emails on their contact/booking/apply page: {contact_page}
2. The producer, booking manager, or guest coordinator
3. Common patterns: contact@, booking@, press@, apply@, hello@, guests@, [firstname]@domain.com

Return ONLY a valid JSON array. Max 4 contacts. No other text:
[{{"email": "email@domain.com", "name": "First Last or null", "role": "host/producer/booking/general", "confidence": "high/medium/low"}}]

Only include emails you actually found or can reasonably guess from their domain pattern."""

def find_contacts(opportunity: dict, retries: int = 3) -> list:
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": PROMPT.format(
                    name=opportunity.get('name', ''),
                    website=opportunity.get('website', ''),
                    contact_page=opportunity.get('contact_page', opportunity.get('website', ''))
                )}]
            )
            full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            contacts = parse_json(full_text)
            filtered = [c for c in contacts if c.get('confidence') != 'low']
            return filtered[:3] if filtered else contacts[:2]

        except anthropic.RateLimitError as e:
            wait = 30 * (attempt + 1)
            print(f"  Rate limit hit, waiting {wait}s before retry {attempt + 1}/{retries}...")
            time.sleep(wait)
        except Exception as e:
            print(f"  Contact finder error: {e}")
            return []

    print(f"  ✗ Failed after {retries} retries")
    return []

def parse_json(text: str) -> list:
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            if part.startswith("json"):
                text = part[4:].strip()
                break
            elif "[" in part:
                text = part.strip()
                break
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return []
