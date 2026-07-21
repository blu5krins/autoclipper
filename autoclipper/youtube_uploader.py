"""YouTube Shorts uploader (free, via YouTube Data API v3).

Supports OAuth flow, direct upload, and scheduled publishing (publishAt).
Tokens are stored per-client on disk under the configured tokens dir.
"""
import os
import json
import threading

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .utils import logger

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Where client secret + tokens live.
CONFIG_DIR = os.environ.get("YT_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "..", "yt_config"))
CLIENT_SECRET_PATH = os.environ.get(
    "YT_CLIENT_SECRET", os.path.join(CONFIG_DIR, "client_secret.json")
)
TOKEN_PATH = os.environ.get("YT_TOKEN", os.path.join(CONFIG_DIR, "token.json"))

# YouTube treats any vertical video <= 60s as a Short automatically when the
# title/hashtag or #Shorts is present. We add #Shorts to be safe.
SHORTS_TAG = "#Shorts"

_lock = threading.Lock()


def _ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def has_client_secret() -> bool:
    return os.path.isfile(CLIENT_SECRET_PATH)


def get_auth_url(redirect_uri: str = None) -> str:
    """Build the OAuth consent URL. Returns None if no client secret is set.

    redirect_uri should be the exact URI registered in Google Cloud Console
    (e.g. http://localhost:5173/). For Web-app OAuth clients this is required.
    """
    if not has_client_secret():
        return None
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_PATH, scopes=SCOPES
    )
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    _save_flow(flow)
    return auth_url


def _flow_path():
    return os.path.join(CONFIG_DIR, "flow_state.json")


def _save_flow(flow):
    _ensure_dirs()
    # Persist only the bits needed to reconstruct the flow for the callback.
    data = {
        "client_config": flow.client_config,
        "scopes": list(SCOPES),
        "redirect_uri": getattr(flow, "redirect_uri", None),
        "state": getattr(flow, "state", None),
        "code_verifier": getattr(flow, "code_verifier", None),
    }
    with open(_flow_path(), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _load_flow():
    if not os.path.isfile(_flow_path()):
        return None
    with open(_flow_path(), "r", encoding="utf-8") as f:
        data = json.load(f)
    # The persisted client_config is flat; Flow expects {"web": {...}} or
    # {"installed": {...}}, so wrap it.
    client_config = data["client_config"]
    if "web" not in client_config and "installed" not in client_config:
        client_config = {"web": client_config}
    flow = Flow.from_client_config(client_config, scopes=data["scopes"])
    flow.redirect_uri = data.get("redirect_uri")
    flow.state = data.get("state")
    if data.get("code_verifier"):
        flow.code_verifier = data["code_verifier"]
    return flow


def exchange_code(code: str, redirect_uri: str = None) -> bool:
    """Exchange an authorization code for tokens and persist them."""
    flow = _load_flow()
    if flow is None:
        if not has_client_secret():
            return False
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRET_PATH, scopes=SCOPES
        )
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_token(creds)
    try:
        os.remove(_flow_path())
    except OSError:
        pass
    return True


def _save_token(creds: Credentials):
    """Legacy global-token persistence (kept for backward compatibility)."""
    _ensure_dirs()
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def _load_token() -> Credentials | None:
    """Legacy global-token loader (kept for backward compatibility)."""
    if not os.path.isfile(TOKEN_PATH):
        return None
    return Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)


def creds_from_json(token_json: str) -> Credentials:
    """Rebuild Credentials from a stored JSON string (per-user token)."""
    return Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)


def _refresh_if_needed(creds: Credentials) -> tuple[Credentials, bool]:
    """Refresh expired creds if possible. Returns (creds, changed)."""
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            return creds, True
        except Exception as e:  # noqa: BLE001
            logger.warning("YouTube token refresh failed: %s", e)
    return creds, False


def is_authenticated(token_json: str = None) -> bool:
    """Check auth for a per-user token JSON (falls back to the global token)."""
    if token_json:
        try:
            creds, _ = _refresh_if_needed(creds_from_json(token_json))
            return not creds.expired
        except Exception:  # noqa: BLE001
            return False
    # Legacy global fallback.
    creds = _load_token()
    if creds is None:
        return False
    creds, changed = _refresh_if_needed(creds)
    if changed:
        _save_token(creds)
    return not creds.expired


def is_user_authenticated(token_json: str | None) -> bool:
    """Strict per-user check: only True if THIS user has a valid token."""
    if not token_json:
        return False
    try:
        creds, _ = _refresh_if_needed(creds_from_json(token_json))
        return not creds.expired
    except Exception:  # noqa: BLE001
        return False


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    publish_at: str = None,
    thumbnail_path: str = None,
    token_json: str = None,
    on_token_changed=None,
) -> dict:
    """Upload a video as a YouTube Short.

    publish_at: ISO 8601 datetime string (e.g. '2026-07-20T10:00:00Z').
    If set, the video is scheduled privately and goes public at that time.
    token_json: per-user OAuth token JSON. If None, the legacy global token
    is used. on_token_changed(creds_json) is called when the token is refreshed.
    Returns the API response dict (contains 'id').
    """
    if token_json:
        creds = creds_from_json(token_json)
    else:
        creds = _load_token()
    if creds is None:
        raise RuntimeError("Not authenticated with YouTube")
    creds, changed = _refresh_if_needed(creds)
    if changed:
        if on_token_changed:
            on_token_changed(creds.to_json())
        else:
            _save_token(creds)

    youtube = build(API_SERVICE_NAME, API_VERSION, credentials=creds)

    base_title = title or "Short"
    if SHORTS_TAG.lower() not in (base_title + " " + (description or "")).lower():
        base_title = f"{base_title} {SHORTS_TAG}"

    # Normalize publishAt: strip milliseconds, ensure UTC 'Z', reject past times.
    norm_publish_at = None
    if publish_at:
        try:
            from datetime import datetime, timezone

            dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # YouTube rejects publishAt in the past; require >= 5 min ahead.
            from datetime import timedelta

            if dt < datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError(
                    "Schedule time must be at least 5 minutes in the future"
                )
            norm_publish_at = dt.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except ValueError as ve:
            raise ValueError(f"Invalid schedule time: {ve}")

    body = {
        "snippet": {
            "title": base_title,
            "description": description or "",
            "tags": ["shorts"],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "private" if norm_publish_at else "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    if norm_publish_at:
        body["status"]["publishAt"] = norm_publish_at

    media = MediaFileUpload(
        video_path, chunksize=-1, resumable=True, mimetype="video/*"
    )
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                logger.info("YouTube upload %d%%", int(status.progress() * 100))
        except Exception as e:  # noqa: BLE001
            logger.error("YouTube upload chunk error: %r", e)
            content = getattr(e, "content", None)
            if content:
                logger.error("YouTube error body: %s", content.decode("utf-8", "replace"))
            raise

    video_id = response.get("id")
    if thumbnail_path and os.path.isfile(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(thumbnail_path)
            ).execute()
        except Exception as e:  # noqa: BLE001
            logger.warning("Thumbnail upload failed: %s", e)

    logger.info("YouTube upload done: %s", video_id)
    return response
