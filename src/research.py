import anthropic
import json
import os
import re

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PROMPT = """Search the web and find 10 NEW speaking/podcast/competition opportunities for a 20-year-old NYC entrepreneur named Ethan Williams.

About Ethan:
- 20 years old, based in NYC
- Founded a software company doing $5M+/year revenue
- Leads a young entrepreneur community called The Taco Project
- Topics: entrepreneurship, gen z mindset, travel/culture, living a full life while building, overcoming struggles
- Looking for: podcasts, speaking panels, pitch competitions, competition/game shows
- Has spoken at schools and entrepreneur groups before

Already contacted (skip these): {already_contacted}

Find opportunities that are actively booking guests, have a real audience, and would respond to a cold pitch.

Categories to find (mix them):
1. Podcasts booking guests — entrepreneurship, culture, mindset, gen z, sneakers, lifestyle
2. Speaking panels/events — NYC startup, entrepreneur panels, college events
3. Business pitch competitions — open to founders, live stage
4. Competition/reality shows — entrepreneurship or lifestyle focused

Return ONLY a valid JSON array. No other text. Each object:
{{
  "name": "platform name",
  "category": "podcast/speaking/competition/show",
  "website": "https://...",
  "contact_page": "https://...",
  "description": "one sentence about what they are",
  "why_fit": "why Ethan fits here specifically"
}}"""

def find_opportunities(already_contacted: list) -> list:
    already_str = ", ".join(already_contacted[-100:]) if already_contacted else "none yet"
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": PROMPT.format(already_contacted=already_str)}]
        )
        full_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
        return parse_json(full_text)
    except Exception as e:
        print(f"Research error: {e}")
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
