"""Viral moment detection using Google Gemini."""
import json
import re

from . import config
from .utils import logger


def _repair_json(text: str) -> str:
    """Fix common Gemini JSON issues: missing commas between array elements."""
    # Insert missing comma between } and { (objects in an array)
    text = re.sub(r'\}\s*\{', '}, {', text)
    # Insert missing comma between ] and [ (arrays in an array)
    text = re.sub(r'\]\s*\[', '], [', text)
    # Remove trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def _build_transcript_text(transcript: dict) -> str:
    """Render segments as timestamped lines for the LLM to reason over."""
    lines = []
    for seg in transcript.get("segments", []):
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{start:.1f} - {end:.1f}] {text}")
    return "\n".join(lines)


PROMPT_TEMPLATE = """You are a viral short-form video editor. Given a timestamped \
transcript of a long video, identify the {count} best self-contained moments that \
would perform well as vertical short clips (TikTok / Reels / YouTube Shorts).

The transcript language is: {language}.
IMPORTANT: Write ALL output fields (title, description, hook, reason) in the SAME \
language as the transcript. If the transcript is Indonesian, write everything in \
natural Indonesian. Do not translate to English unless the transcript itself is in \
English.

Rules:
- Each clip must be between {min_s:.0f} and {max_s:.0f} seconds long.
- Clips must start and end on natural sentence boundaries (no mid-sentence cuts).
- Content focus: {focus}
- Do not overlap clips. Use timestamps that exist in the transcript.
- "start" and "end" are in seconds (numbers).

  Return ONLY valid JSON in exactly this shape, with no markdown fences:
  {{
    "clips": [
      {{
        "start": 12.3,
        "end": 48.9,
        "title": "punchy viral title (max 60 chars)",
        "description": "engaging social caption with 3-5 relevant hashtags (max 200 chars)",
        "hook": "one-line on-screen hook text",
        "reason": "why this moment is compelling"
      }}
    ]
  }}

TRANSCRIPT:
{transcript}
"""


def find_viral_clips(transcript: dict, api_key: str = None, model: str = None,
                      clip_count: int = None, min_clip: float = None,
                      max_clip: float = None, content_type: str = None) -> list:
    """Ask Gemini for a list of viral clip candidates. Returns a list of dicts."""
    from google import genai

    api_key = config.require(api_key or config.GEMINI_API_KEY, "GEMINI_API_KEY")
    model = model or config.GEMINI_MODEL

    count = clip_count or config.TARGET_CLIP_COUNT
    min_s = min_clip if min_clip is not None else config.MIN_CLIP_SECONDS
    max_s = max_clip if max_clip is not None else config.MAX_CLIP_SECONDS

    ctype = config.CONTENT_TYPES.get(content_type, config.CONTENT_TYPES["general"])
    focus = ctype["focus"]

    transcript_text = _build_transcript_text(transcript)
    if not transcript_text.strip():
        raise RuntimeError("Transcript is empty; cannot analyze for clips.")

    language = transcript.get("language") or "auto-detected"
    prompt = PROMPT_TEMPLATE.format(
        count=count,
        min_s=min_s,
        max_s=max_s,
        language=language,
        focus=focus,
        transcript=transcript_text,
    )

    logger.info("Analyzing transcript with Gemini model '%s'...", model)
    client = genai.Client(api_key=api_key)
    response = config.gemini_generate(client, model, prompt)
    raw = (response.text or "").strip()

    clips = _parse_clips(raw)
    clips = _validate_clips(clips, total_duration=transcript.get("duration", 0.0))
    logger.info("Found %d viral clip candidate(s)", len(clips))
    return clips


def _parse_clips(raw: str) -> list:
    """Parse the model output, tolerating markdown fences and bare arrays."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip a ```json ... ``` fence.
        text = text.split("```", 2)[1] if "```" in text else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()

    # Extract the outermost JSON object or array if wrapped in prose.
    if not (text.startswith("{") or text.startswith("[")):
        for opener, closer in (("{", "}"), ("[", "]")):
            first, last = text.find(opener), text.rfind(closer)
            if first != -1 and last != -1 and last > first:
                text = text[first : last + 1]
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json(text)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Could not parse Gemini response as JSON: {e}\nRaw: {raw[:500]}")

    if isinstance(data, list):
        return data
    return data.get("clips", []) if isinstance(data, dict) else []


def _validate_clips(clips: list, total_duration: float) -> list:
    valid = []
    for c in clips:
        try:
            start = float(c["start"])
            end = float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        if total_duration and end > total_duration + 1:
            end = total_duration
        length = end - start
        if length < config.MIN_CLIP_SECONDS - 2 or length > config.MAX_CLIP_SECONDS + 5:
            continue
        valid.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "title": (c.get("title") or "Untitled Clip").strip()[:80],
                "description": (c.get("description") or "").strip()[:220],
                "hook": (c.get("hook") or "").strip()[:120],
                "reason": (c.get("reason") or "").strip(),
            }
        )
    valid.sort(key=lambda x: x["start"])
    return valid
