import anthropic
import json
import os
import re
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

RESEARCH_PROMPT = """Search the web and find {per_session} NEW podcast shows or public speaking events that are a great fit for Ethan Williams (20yo NYC founder, $5M+ software company, The Taco Project community).

Target: actively booking guests, 1k-100k audience, entrepreneurship/gen z/fintech/lifestyle/sneakers focus.
Skip: mega-famous shows, pitch competitions, already-contacted platforms.

Already contacted (skip these): {already_contacted}

Search thoroughly, then provide your findings."""

EXTRACT_PROMPT = """Convert the research findings below into a JSON array. Return ONLY the JSON array, nothing else — no markdown, no explanation, no code fences.

Research findings:
{research_text}

JSON format (return exactly this structure, {per_session} items):
[{{"name":"Platform Name","category":"podcast","website":"https://example.com","contact_page":"https://example.com/contact","description":"One sentence about them","why_fit":"Why Ethan fits here"}}]

Return the raw JSON array only:"""

def find_opportunities(already_contacted: list, config: dict = None, retries: int = 3) -> list:
    cfg = config or {}
    research_prompt_template = cfg.get("researchPrompt", "")
    per_session = cfg.get("perSession", 15)

    # Use last 20 only to avoid prompt bloat
    already_str = ", ".join(already_contacted[-20:]) if already_contacted else "none"

    for attempt in range(retries):
        try:
            # Step 1: Research with web search (let it write freely)
            research_q = (research_prompt_template or RESEARCH_PROMPT).replace(
                "{already_contacted}", already_str
            ).replace("{per_session}", str(per_session))

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": research_q}]
            )
            research_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            print(f"  Research response length: {len(research_text)} chars")

            # Try parsing directly first (in case it did return JSON)
            results = parse_json(research_text)
            if results:
                print(f"  Found {len(results)} opportunities (direct parse)")
                return results[:per_session]

            # Step 2: Extract as JSON using a separate call (no web search)
            extract_prompt = EXTRACT_PROMPT.replace("{research_text}", research_text[:3000]).replace("{per_session}", str(per_session))
            extract_response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": extract_prompt}]
            )
            json_text = extract_response.content[0].text if extract_response.content else ""
            print(f"  Extract response length: {len(json_text)} chars, preview: {json_text[:100]}")

            results = parse_json(json_text)
            if results:
                print(f"  Found {len(results)} opportunities (extract step)")
                return results[:per_session]

            print(f"  Still empty after extract (attempt {attempt + 1}/{retries})")
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
    # Strip code fences
    for fence in ["```json", "```"]:
        if fence in text:
            parts = text.split(fence)
            for part in parts:
                stripped = part.strip().rstrip("`").strip()
                if stripped.startswith("["):
                    text = stripped
                    break
    # Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list) and result:
            return result
    except:
        pass
    # Find array in text
    match = re.search(r'\[[\s\S]*?\]', text)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list) and result:
                return result
        except:
            pass
    # Collect individual objects
    objects = re.findall(r'\{[^{}]*"name"[^{}]*\}', text, re.DOTALL)
    valid = []
    for obj in objects:
        try:
            parsed = json.loads(obj)
            if parsed.get("name"):
                valid.append(parsed)
        except:
            pass
    return valid
