"""YouTube "Explore" data via the YouTube Data API v3.

NOTE: YouTube retired the Trending page in July 2025 and replaced it with the
"Explore" section (destination pages per category: Music, Gaming, News, etc.).
This module mirrors that by pulling the most-popular videos for a region
(`videos.list chart=mostPopular`, which still supports `regionCode`) and
filtering them by the official `videoCategoryId` of each Explore category.

Shorts (<60s) and live streams are filtered out. Podcast mode keeps only
longer-form talk content (>10 min).
"""
import json
import time
import urllib.parse
import urllib.request

from . import config
from .utils import logger


# Official YouTube video categories, used as Explore destination pages.
# key -> (YouTube categoryId, human label)
CATEGORY_MAP = {
    "general":     ("0",  "Explore"),
    "music":       ("10", "Music"),
    "gaming":      ("20", "Gaming"),
    "news":        ("25", "News"),
    "sports":      ("17", "Sports"),
    "entertainment": ("24", "Entertainment"),
    "education":   ("27", "Education"),
    "tech":        ("28", "Tech & Science"),
    "howto":       ("26", "Howto & Style"),
    "people":      ("22", "People & Blogs"),
    "podcast":     ("22", "Podcasts"),
    "movies":      ("30", "Movies"),
    "anime":       ("31", "Anime & Animation"),
    "vehicles":    ("2",  "Autos & Vehicles"),
    "comedy":      ("23", "Comedy"),
    "shows":       ("29", "Shows"),
    "trailers":    ("44", "Trailers"),
}

# Ordered list for the Explore tab UI.
EXPLORE_CATEGORIES = [
    "general", "music", "gaming", "news", "sports", "entertainment",
    "education", "tech", "howto", "people", "podcast", "movies",
    "anime", "vehicles", "comedy", "shows", "trailers",
]

REGION_MAP = {
    "id": "ID",
    "us": "US",
    "gb": "GB",
    "kr": "KR",
    "jp": "JP",
    "in": "IN",
}

REGION_MAP = {
    "id": "ID",
    "us": "US",
    "gb": "GB",
    "kr": "KR",
    "jp": "JP",
    "in": "IN",
}

API_BASE = "https://www.googleapis.com/youtube/v3"


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "AutoClipper/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_iso_duration(iso: str) -> int:
    """Convert YouTube ISO-8601 duration (e.g. PT1H2M3S) to seconds."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def fetch_trending(api_key: str, region: str = "ID", category: str = "general",
                   max_results: int = 12, window_days: int = 3) -> list:
    """Return Explore-style most-popular videos for a region, filtered by category.

    Uses videos.list chart=mostPopular (still supports regionCode). The chosen
    Explore category is applied as a hard filter on the video's snippet.categoryId
    (mostPopular returns mixed categories per region). Shorts (<60s) and live
    streams are filtered out; podcast mode keeps only longer talk content (>10min).
    """
    if not api_key:
        raise RuntimeError("YouTube API key required (set YOUTUBE_API_KEY or provide api_key).")

    region = (REGION_MAP.get(region.lower(), region) if region else "ID").upper()
    cat_entry = CATEGORY_MAP.get(category, ("0", "Explore"))
    cat_id = cat_entry[0]

    # 1. Most-popular chart supports regionCode reliably.
    params = urllib.parse.urlencode({
        "part": "snippet,statistics,contentDetails,liveStreamingDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "maxResults": 50,  # fetch max so we can filter by category client-side
        "key": api_key,
    })
    url = f"{API_BASE}/videos?{params}"
    logger.info("Fetching Explore (region=%s category=%s)...", region, category)
    data = _http_get_json(url)

    items = data.get("items", [])
    if not items:
        return []

    videos = []
    for it in items:
        vid = it["id"]
        sn = it.get("snippet", {})
        st = it.get("statistics", {})
        cd = it.get("contentDetails", {})
        dur = _parse_iso_duration(cd.get("duration", ""))

        # Explore category filter via categoryId (general = no filter).
        if category != "general" and sn.get("categoryId", "") != cat_id:
            continue

        # Skip Shorts: very short videos (<60s) OR titles mentioning "shorts".
        title_lc = (sn.get("title", "") or "").lower()
        is_short_by_duration = dur > 0 and dur < 60
        is_short_by_title = "shorts" in title_lc
        if is_short_by_duration or is_short_by_title:
            continue
        # Skip live streams still in progress.
        if "liveStreamingDetails" in it:
            continue
        # Podcast mode: only longer-form talk content (>10 min).
        if category == "podcast" and dur > 0 and dur < 600:
            continue
        # General / others: skip ultra-long VODs (>3h) to keep it short-form friendly.
        if category != "podcast" and dur > 10800:
            continue

        videos.append({
            "video_id": vid,
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "published_at": sn.get("publishedAt", ""),
            "thumbnail": (sn.get("thumbnails", {}).get("medium")
                          or sn.get("thumbnails", {}).get("default", {})).get("url", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),
            "duration_sec": dur,
        })
        if len(videos) >= max_results:
            break
    return videos


ENRICH_PROMPT = """You are a viral short-form video strategist. Below is a list of \
YouTube videos that are currently TRENDING in the "{niche}" niche. For each, write \
a short, practical idea on how a creator could ride this trend — e.g. a reaction, \
a clip breakdown, a POV, or a "watch along" short.

Write in the SAME language as the video titles when possible. Keep each idea to \
one punchy sentence.

Return ONLY valid JSON in exactly this shape (no markdown fences):
{{
  "insights": [
    {{ "video_id": "VIDEO_ID", "idea": "one-sentence clip/repurpose idea" }}
  ]
}}

TRENDING VIDEOS:
{lines}
"""


def enrich_trending(videos: list, niche: str = "general",
                    api_key: str = None, model: str = None) -> dict:
    """Ask Gemini to suggest clip ideas based on real trending videos."""
    from google import genai

    gem_key = api_key or config.GEMINI_API_KEY
    if not gem_key:
        return {}
    model = model or config.GEMINI_MODEL

    lines = "\n".join(
        f"- [{v['video_id']}] {v['title']} (by {v['channel']}, {v['views']} views)"
        for v in videos
    )
    prompt = ENRICH_PROMPT.format(niche=niche or "general", lines=lines)

    logger.info("Enriching %d trending videos with Gemini...", len(videos))
    client = genai.Client(api_key=gem_key)
    response = config.gemini_generate(client, model, prompt)
    raw = (response.text or "").strip()

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
    except json.JSONDecodeError:
        return {}
    return {x.get("video_id"): x.get("idea", "") for x in data.get("insights", [])}
