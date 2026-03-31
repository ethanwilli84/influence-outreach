import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def find_opportunities(already_contacted: list, config: dict = None, retries: int = 3) -> list:
    # Use research prompt from admin config, fall back to default
    prompt_template = (config or {}).get("researchPrompt", "")
    per_session = (config or {}).get("perSession", 15)

    if not prompt_template:
        prompt_template = """Search the web and find {per_session} NEW podcast or public speaking opportunities for a 20-year-old NYC entrepreneur named Ethan Williams.

About Ethan:
- 20 years old, based in NYC
- Founded a software company doing $5M+/year revenue
- Leads a young entrepreneur community called The Taco Project
- Topics: entrepreneurship, gen z mindset, travel/culture, living a full life while building, overcoming struggles
- Has spoken at schools and entrepreneur groups before
- No large public following yet — his credibility is his story and substance, not fame

Target platforms with 1,000–100,000 listeners/followers. Avoid mega-famous shows.
Focus on: college entrepreneurship events, NYC startup panels, niche podcasts (sneakers, fintech, gen z, young money).
Do NOT include pitch competitions or formats requiring prepared materials.

Already contacted (skip these): {already_contacted}

Return ONLY a valid JSON array of {per_session} objects. No other text:
[{{"name":"...","category":"podcast|speaking","website":"...","contact_page":"...","description":"...","why_fit":"..."}}]"""

    already_str = ", ".join(already_contacted[-100:]) if already_contacted else "none yet"
    prompt = prompt_template.replace("{already_contacted}", already_str).replace("{per_session}", str(per_session))

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}]
            )
            full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            results = parse_json(full_text)
            if results:
                return results[:per_session]
            print(f"  Research returned empty, retry {attempt + 1}/{retries}...")
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
