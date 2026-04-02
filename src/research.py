import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def find_opportunities(already_contacted: list, config: dict = None, retries: int = 3) -> list:
    prompt_template = (config or {}).get("researchPrompt", "")
    per_session = (config or {}).get("perSession", 15)

    if not prompt_template:
        prompt_template = """Search the web and find {per_session} NEW podcast or public speaking opportunities for a 20-year-old NYC entrepreneur named Ethan Williams.

About Ethan:
- 20 years old, based in NYC
- Founded a software company doing $5M+/year revenue
- Leads a young entrepreneur community called The Taco Project
- Topics: entrepreneurship, gen z mindset, travel/culture, living a full life while building
- Has spoken at schools and entrepreneur groups before
- No large public following yet — credibility is his story

Target platforms with 1,000–100,000 listeners/followers that are actively growing and booking guests.
Focus on: college entrepreneurship events, NYC startup panels, niche podcasts (sneakers, fintech, gen z, young money, B2B, lifestyle).
Do NOT include pitch competitions or formats requiring prepared materials.

Skip these already-contacted platforms: {already_contacted}

Return ONLY a valid JSON array. No markdown, no explanation, no code fences. Just the raw JSON array:
[{{"name":"...","category":"podcast|speaking","website":"https://...","contact_page":"https://...","description":"one sentence","why_fit":"why Ethan fits"}}]"""

    # Only pass last 20 to avoid prompt bloat
    already_str = ", ".join(already_contacted[-20:]) if already_contacted else "none"
    prompt = prompt_template.replace("{already_contacted}", already_str).replace("{per_session}", str(per_session))

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            # Collect all text blocks from response
            full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            print(f"  Research response length: {len(full_text)} chars")

            results = parse_json(full_text)
            if results:
                print(f"  Found {len(results)} opportunities")
                return results[:per_session]

            print(f"  Research returned empty (attempt {attempt + 1}/{retries}), response preview: {full_text[:200]}")
            time.sleep(15)

        except anthropic.RateLimitError:
            wait = 45 * (attempt + 1)
            print(f"  Research rate limit, waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"Research error: {e}")
            time.sleep(15)

    print("Research failed after all retries")
    return []

def parse_json(text: str) -> list:
    """Extract a JSON array from text, handling various formats."""
    text = text.strip()

    # Strip code fences
    if "```" in text:
        for part in text.split("```"):
            stripped = part.strip()
            if stripped.startswith("json"):
                text = stripped[4:].strip()
                break
            elif stripped.startswith("["):
                text = stripped
                break

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except:
        pass

    # Find JSON array anywhere in the text
    match = re.search(r'\[[\s\S]*?\]', text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except:
            pass

    # Try finding individual JSON objects and collecting them
    objects = re.findall(r'\{[^{}]+\}', text, re.DOTALL)
    if objects:
        valid = []
        for obj in objects:
            try:
                parsed = json.loads(obj)
                if parsed.get('name') and parsed.get('category'):
                    valid.append(parsed)
            except:
                pass
        if valid:
            return valid

    return []
