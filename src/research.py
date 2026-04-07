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

def find_opportunities(already_contacted: list, config: dict = None, retries: int = 3) -> list:
    cfg = config or {}
    research_prompt_template = cfg.get("researchPrompt", "")
    per_session = cfg.get("perSession", 15)

    # Pass up to 60 — enough context for research to avoid repeats
    # Truncate each name to keep prompt manageable
    already_list = [str(x)[:50] for x in list(already_contacted)[-60:]]
    already_str = ", ".join(already_list) if already_list else "none"

    for attempt in range(retries):
        try:
            # Step 1: Research with web search — enforce anti-hallucination
            research_q = (research_prompt_template or RESEARCH_PROMPT).replace(
                "{already_contacted}", already_str
            ).replace("{per_session}", str(per_session)) + """

CRITICAL RULES:
- Run web_search at least 4 times with DIFFERENT angles — vary by niche, geography, audience size, platform type
- DO NOT repeat any company from the already-contacted list above — that is a hard skip
- Prioritize OBSCURE and NICHE targets over well-known ones (they have less competition in their inbox)
- Report ONLY what you actually found with verified real URLs
- If you can only verify 5 real ones after searching, return 5 — quality beats quota
- NEVER invent Placeholder entries under any circumstances"""

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=6000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": research_q}]
            )
            research_text = "".join(b.text for b in response.content if hasattr(b, 'text'))
            print(f"  Research response length: {len(research_text)} chars")

            # Try parsing directly first (in case it did return JSON)
            results = parse_json(research_text)
            if results:
                results = [r for r in results if r.get("name") and "placeholder" not in r.get("name","").lower() and len(r.get("name","")) > 3]
                print(f"  Found {len(results)} opportunities (direct parse)")
                return results[:per_session]

            # Step 2: Extract as JSON using a separate call (no web search)
            extract_prompt = EXTRACT_PROMPT.replace("{research_text}", research_text[:3000])
            extract_response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": extract_prompt}]
            )
            json_text = extract_response.content[0].text if extract_response.content else ""
            print(f"  Extract response length: {len(json_text)} chars, preview: {json_text[:100]}")

            results = parse_json(json_text)
            if results:
                # Hard filter: drop AI-hallucinated placeholders
                results = [r for r in results 
                    if r.get("name") 
                    and "placeholder" not in r.get("name","").lower()
                    and r.get("name","").strip()
                    and len(r.get("name","")) > 3
                ]
                print(f"  Found {len(results)} real opportunities (extract step)")
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
