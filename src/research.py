import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROMPT = """Search the web and find 10 NEW speaking/podcast/competition opportunities for a 20-year-old NYC entrepreneur named Ethan Williams.

About Ethan:
- 20 years old, based in NYC
- Founded a software company doing $5M+/year revenue
- Leads a young entrepreneur community called The Taco Project
- Topics: entrepreneurship, gen z mindset, travel/culture, living a full life while building, overcoming struggles
- Has spoken at schools and entrepreneur groups before
- No large public following yet — his credibility is his story and substance, not fame

IMPORTANT — Target platform size:
Look for platforms that are ACTIVELY GROWING but not mega-famous. Ethan has no public following yet so massive shows like Full Send, No Jumper, Ed Mylett, or Joe Rogan will NOT respond to a cold pitch from someone unknown. Avoid these.

Instead target:
- Podcasts with 1,000–100,000 listeners/followers that are hungry for interesting guests
- Up and coming hosts who are building their audience and book guests based on story quality, not fame
- College and university entrepreneurship events, panels, and podcasts
- Local NYC startup/entrepreneur events and panels
- Niche podcasts in sneakers, reselling, fintech, gen z, young money, lifestyle
- Pitch competitions open to any founder
- Smaller competition/reality formats that are actively casting

The sweet spot: platforms big enough that appearing on them is worthwhile, small enough that they'll actually respond to a cold pitch from a compelling unknown.

Already contacted (skip these): {already_contacted}

Categories to find (mix them):
1. Podcasts booking guests — entrepreneurship, culture, mindset, gen z, sneakers, lifestyle
2. Speaking panels/events — NYC startup, entrepreneur panels, college events
3. Business pitch competitions — open to any founder, live stage
4. Competition/reality shows — entrepreneurship or lifestyle focused, actively casting

Return ONLY a valid JSON array. No other text. Each object:
{{
  "name": "platform name",
  "category": "podcast/speaking/competition/show",
  "website": "https://...",
  "contact_page": "https://...",
  "description": "one sentence about what they are",
  "why_fit": "why Ethan fits here specifically"
}}"""

def find_opportunities(already_contacted: list, retries: int = 3) -> list:
    already_str = ", ".join(already_contacted[-100:]) if already_contacted else "none yet"

    for attempt in range(retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": PROMPT.format(already_contacted=already_str)}]
            )
            full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            results = parse_json(full_text)
            if results:
                return results
            print(f"  Research returned empty, retry {attempt + 1}/{retries}...")
            time.sleep(15)

        except anthropic.RateLimitError:
            wait = 45 * (attempt + 1)
            print(f"  Research rate limit, waiting {wait}s before retry {attempt + 1}/{retries}...")
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
