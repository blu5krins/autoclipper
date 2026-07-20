"""Trending video ideas using Google Gemini.

Generates platform-aware, viral short-video content ideas that creators can
record or repurpose. No external API keys beyond Gemini are required.
"""
import json

from . import config
from .utils import logger


TRENDING_PROMPT = """You are a viral short-form video strategist. Based on current \
social media trends (TikTok, YouTube Shorts, Instagram Reels), suggest {count} \
high-potential short video ideas for the niche: "{niche}".

For each idea, provide:
- A punchy title / hook (max 60 chars)
- A one-line description of the video concept
- The best platform fit (Shorts / TikTok / Reels / All)
- A content format (e.g. "Trend hijack", "Storytime", "Tutorial", "Reaction", "POV")
- 3-5 relevant hashtags
- Why it has viral potential right now (one line)

Return ONLY valid JSON in exactly this shape, with no markdown fences:
{{
  "ideas": [
    {{
      "title": "punchy hook title",
      "concept": "one-line description of the video concept",
      "platform": "Shorts | TikTok | Reels | All",
      "format": "Trend hijack | Storytime | Tutorial | Reaction | POV | Challenge | List",
      "hashtags": ["#tag1", "#tag2", "#tag3"],
      "why": "why this is trending / has viral potential"
    }}
  ]
}}
"""


def get_trending_ideas(niche: str = "general", api_key: str = None,
                       model: str = None, count: int = 10) -> list:
    """Ask Gemini for trending short-video ideas. Returns a list of dicts."""
    from google import genai

    api_key = config.require(api_key or config.GEMINI_API_KEY, "GEMINI_API_KEY")
    model = model or config.GEMINI_MODEL

    count = max(3, min(count or 10, 20))
    prompt = TRENDING_PROMPT.format(niche=niche or "general", count=count)

    logger.info("Generating trending ideas for niche '%s' with model '%s'...", niche, model)
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=prompt)
    raw = (response.text or "").strip()

    ideas = _parse_ideas(raw)
    logger.info("Generated %d trending idea(s)", len(ideas))
    return ideas


def _parse_ideas(raw: str) -> list:
    """Parse the model output, tolerating markdown fences and prose wrapping."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()

    if not (text.startswith("{") or text.startswith("[")):
        for opener, closer in (("{", "}"), ("[", "]")):
            first, last = text.find(opener), text.rfind(closer)
            if first != -1 and last != -1 and last > first:
                text = text[first : last + 1]
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse Gemini response as JSON: {e}\nRaw: {raw[:500]}")

    if isinstance(data, list):
        return data
    return data.get("ideas", []) if isinstance(data, dict) else []
