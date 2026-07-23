"""Facebook Pages video uploader via Graph API (Resumable Upload).

Supports OAuth flow, Page selection, and video upload/reels.
"""
import os
import json
import time
import threading
import requests

from .utils import logger

GRAPH_URL = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO_URL = "https://graph-video.facebook.com/v21.0"

SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "publish_video",
]

CONFIG_DIR = os.environ.get(
    "FB_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "fb_config")
)
TOKEN_PATH = os.environ.get("FB_TOKEN", os.path.join(CONFIG_DIR, "token.json"))

_lock = threading.Lock()


def _ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def get_auth_url(app_id: str, redirect_uri: str) -> str:
    """Build Facebook Login OAuth URL."""
    scope = ",".join(SCOPES)
    return (
        f"https://www.facebook.com/v21.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&response_type=code"
    )


def exchange_code(app_id: str, app_secret: str, code: str, redirect_uri: str) -> dict:
    """Exchange authorization code for short-lived user token."""
    resp = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data


def exchange_long_lived(user_token: str, app_id: str, app_secret: str) -> dict:
    """Exchange short-lived token for long-lived token (~60 days)."""
    resp = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": user_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_pages(user_token: str) -> list[dict]:
    """Fetch Pages the user has access to."""
    resp = requests.get(
        f"{GRAPH_URL}/me/accounts",
        params={"access_token": user_token, "fields": "id,name,access_token,category"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def save_token(data: dict):
    """Persist token data to disk."""
    _ensure_dirs()
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_token() -> dict | None:
    """Load persisted token data."""
    if not os.path.isfile(TOKEN_PATH):
        return None
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_authenticated(token_data: dict = None) -> bool:
    """Check if we have a valid (non-expired) token."""
    data = token_data or load_token()
    if not data:
        return False
    expires = data.get("expires_at", 0)
    return time.time() < expires - 300  # 5 min safety margin


def get_user_info(user_token: str) -> dict | None:
    """Fetch basic user info to verify token validity."""
    try:
        resp = requests.get(
            f"{GRAPH_URL}/me",
            params={"access_token": user_token, "fields": "id,name,email"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("Facebook user info fetch failed: %s", e)
        return None


def _start_upload_session(
    app_id: str, user_token: str, file_name: str, file_length: int, file_type: str
) -> str:
    """Start a resumable upload session. Returns session ID."""
    resp = requests.post(
        f"{GRAPH_URL}/{app_id}/uploads",
        params={
            "file_name": file_name,
            "file_length": file_length,
            "file_type": file_type,
            "access_token": user_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _upload_chunk(
    user_token: str, session_id: str, data: bytes, offset: int
) -> dict:
    """Upload a chunk of file data."""
    resp = requests.post(
        f"{GRAPH_URL}/upload:{session_id}",
        headers={
            "Authorization": f"OAuth {user_token}",
            "file_offset": str(offset),
        },
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def upload_video_to_page(
    video_path: str,
    page_id: str,
    page_access_token: str,
    title: str = "",
    description: str = "",
    as_reel: bool = False,
    user_token: str = None,
    app_id: str = None,
) -> dict:
    """Upload a video to a Facebook Page using Resumable Upload API.

    video_path: local path to the video file
    page_id: target Facebook Page ID
    page_access_token: Page access token with pages_manage_posts permission
    title: video title
    description: video description
    as_reel: if True, publish as Reel
    user_token: user access token (needed for upload session)
    app_id: Facebook App ID (needed for upload session)
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_name = os.path.basename(video_path)
    file_length = os.path.getsize(video_path)
    file_type = "video/mp4"

    # Use page token for upload session if no user token provided
    upload_token = user_token or page_access_token
    upload_app_id = app_id or "me"

    logger.info("Facebook: starting upload session for %s (%d MB)", file_name, file_length // (1024 * 1024))

    # Step 1: Start upload session
    session_id = _start_upload_session(
        upload_app_id, upload_token, file_name, file_length, file_type
    )
    logger.info("Facebook: upload session %s started", session_id)

    # Step 2: Upload file in chunks (10 MB chunks)
    CHUNK_SIZE = 10 * 1024 * 1024
    offset = 0

    with open(video_path, "rb") as f:
        while offset < file_length:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            _upload_chunk(upload_token, session_id, chunk, offset)
            offset += len(chunk)
            pct = int(offset / file_length * 100)
            logger.info("Facebook upload: %d%%", pct)

    logger.info("Facebook: upload complete, publishing to page %s", page_id)

    # Step 3: Publish video to Page
    publish_data = {
        "title": title or "Video",
        "description": description or "",
        "uploaded_video": session_id,
        "access_token": page_access_token,
    }

    if as_reel:
        publish_data["upload_settings"] = '{"upload_phase":"finish","upload_session_id":"%s"}' % session_id

    resp = requests.post(
        f"{GRAPH_URL}/{page_id}/videos",
        data=publish_data,
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()

    video_id = result.get("id")
    logger.info("Facebook: video published as %s", video_id)

    return {
        "video_id": video_id,
        "post_id": result.get("post_id"),
        "url": f"https://www.facebook.com/reel/{video_id}" if as_reel else f"https://www.facebook.com/video/{video_id}",
    }


def get_page_videos(page_id: str, page_token: str, limit: int = 10) -> list[dict]:
    """Fetch recent videos from a Page."""
    resp = requests.get(
        f"{GRAPH_URL}/{page_id}/videos",
        params={
            "access_token": page_token,
            "fields": "id,title,description,created_time,length",
            "limit": limit,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
