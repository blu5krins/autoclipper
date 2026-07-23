"""TikTok upload via Playwright + session cookies.

Flow:
  1. User exports cookies from browser (Cookie-Editor JSON or Netscape txt)
  2. Cookies are stored encrypted in the DB (tiktok_cookies column)
  3. Account info is fetched via TikTok internal API
  4. Upload uses Playwright to drive the real tiktok.com/upload page
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Cookie helpers ──────────────────────────────────────────────────────────

def parse_cookies(raw: str) -> list[dict]:
    """Parse cookies from either Cookie-Editor JSON or Netscape txt format.

    Returns a list of dicts suitable for Playwright ``context.add_cookies()``.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty cookies input")

    # Try JSON first (Cookie-Editor export)
    if raw.startswith("[") or raw.startswith("{"):
        return _parse_json_cookies(raw)

    # Fallback: Netscape / cookies.txt format
    return _parse_netscape_cookies(raw)


def _parse_json_cookies(raw: str) -> list[dict]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("cookies", [data]) if "cookies" in data else [data]
    out = []
    for c in data:
        domain = c.get("domain", "")
        if not domain:
            continue
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": domain,
            "path": c.get("path", "/"),
        }
        if c.get("expirationDate"):
            cookie["expires"] = c["expirationDate"]
        if c.get("secure"):
            cookie["secure"] = True
        if c.get("httpOnly"):
            cookie["httpOnly"] = True
        out.append(cookie)
    return out


def _parse_netscape_cookies(raw: str) -> list[dict]:
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, expires, name, value = parts[:7]
        if not domain.endswith("tiktok.com"):
            continue
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
        }
        if expires and expires != "0":
            try:
                cookie["expires"] = int(expires)
            except ValueError:
                pass
        if secure.upper() == "TRUE":
            cookie["secure"] = True
        out.append(cookie)
    return out


def validate_tiktok_cookies(cookies: list[dict]) -> bool:
    """Check that the cookie list contains essential TikTok session cookies."""
    names = {c["name"] for c in cookies}
    # sessionid is the primary auth cookie; sessionid_ss is the secure variant
    return "sessionid" in names or "sessionid_ss" in names


# ── Account info ────────────────────────────────────────────────────────────

TIKTOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.tiktok.com/",
}

_EMPTY_ACCOUNT = {
    "unique_id": "",
    "nickname": "",
    "avatar": "",
    "signature": "",
    "follower_count": 0,
    "following_count": 0,
    "likes_count": 0,
    "video_count": 0,
    "verified": False,
    "private_account": False,
}


def _extract_account(data: dict) -> dict:
    """Extract account info from TikTok rehydration data."""
    user_info = (
        data.get("__DEFAULT_SCOPE__", {})
        .get("webapp.user-detail", {})
        .get("userInfo", {})
        .get("user", {})
    )
    stats = (
        data.get("__DEFAULT_SCOPE__", {})
        .get("webapp.user-detail", {})
        .get("userInfo", {})
        .get("stats", {})
    )
    if not user_info:
        return {}
    return {
        "unique_id": user_info.get("uniqueId", ""),
        "nickname": user_info.get("nickname", ""),
        "avatar": user_info.get("avatarLarger", user_info.get("avatarMedium", "")),
        "signature": user_info.get("signature", ""),
        "follower_count": stats.get("followerCount", 0),
        "following_count": stats.get("followingCount", 0),
        "likes_count": stats.get("heartCount", 0),
        "video_count": stats.get("videoCount", 0),
        "verified": user_info.get("verified", False),
        "private_account": user_info.get("privateAccount", False),
    }


async def fetch_account_info(cookies_json: str) -> dict:
    """Fetch the connected TikTok user's profile info using Patchright.

    Patchright is a patched Playwright that bypasses bot detection.
    Strategy: navigate to TikTok, intercept responses for user data.
    """
    from patchright.async_api import async_playwright

    cookies = parse_cookies(cookies_json)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=TIKTOK_HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
        )
        await context.add_cookies(cookies)
        page = await context.new_page()

        captured_user = {}
        all_response_urls = []

        async def on_response(response):
            nonlocal captured_user
            url = response.url
            all_response_urls.append(url)
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    body_text = await response.text()
                    if "uniqueId" in body_text and "nickname" in body_text:
                        import re
                        uid_match = re.search(r'"uniqueId"\s*:\s*"([^"]+)"', body_text)
                        nn_match = re.search(r'"nickname"\s*:\s*"([^"]+)"', body_text)
                        if uid_match and nn_match:
                            uid_val = uid_match.group(1)
                            nn_val = nn_match.group(1)
                            if uid_val and uid_val not in ("", "null") and nn_val:
                                captured_user = {
                                    "unique_id": uid_val,
                                    "nickname": nn_val,
                                    "avatar": "",
                                    "signature": "",
                                    "follower_count": 0,
                                    "following_count": 0,
                                    "likes_count": 0,
                                    "video_count": 0,
                                    "verified": False,
                                    "private_account": False,
                                }
                                print(f"[TIKTOK DEBUG] Captured from response {url}: @{uid_val}")
            except Exception:
                pass

        page.on("response", on_response)

        try:
            print("[TIKTOK DEBUG] Navigating to TikTok (patchright)...")
            await page.goto(
                "https://www.tiktok.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(8000)

            print(f"[TIKTOK DEBUG] Captured user: {captured_user}")
            print(f"[TIKTOK DEBUG] Response URLs count: {len(all_response_urls)}")
            for u in all_response_urls[:30]:
                print(f"  [URL] {u[:120]}")

            if captured_user and captured_user.get("unique_id"):
                return captured_user

            # Try extracting from rehydration data
            info2 = await page.evaluate("""() => {
                try {
                    const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                    if (!el) return { error: 'no rehydration element' };
                    const data = JSON.parse(el.textContent);
                    const scope = data?.['__DEFAULT_SCOPE__'] || {};
                    let user = scope['webapp.user-detail']?.userInfo?.user;
                    let stats = scope['webapp.user-detail']?.userInfo?.stats;
                    if (!user) user = scope['webapp.self-pInfo']?.user;
                    if (!user || !user.uniqueId) return { error: 'no user in rehydration', keys: Object.keys(scope) };
                    return {
                        unique_id: user.uniqueId || '',
                        nickname: user.nickname || '',
                        avatar: user.avatarLarger || '',
                        signature: user.signature || '',
                        follower_count: stats?.followerCount || 0,
                        following_count: stats?.followingCount || 0,
                        likes_count: stats?.heartCount || 0,
                        video_count: stats?.videoCount || 0,
                        verified: user.verified || false,
                        private_account: user.privateAccount || false,
                    };
                } catch(e) {
                    return { error: e.toString() };
                }
            }""")
            print(f"[TIKTOK DEBUG] Rehydration: {info2}")
            if info2 and info2.get("unique_id"):
                return info2

            # Try self-info API from within the page
            info3 = await page.evaluate("""async () => {
                try {
                    const resp = await fetch('/api/user/info/self/', {
                        credentials: 'include',
                        headers: { 'Accept': 'application/json' }
                    });
                    const text = await resp.text();
                    const data = JSON.parse(text);
                    const user = data?.userInfo?.user;
                    const stats = data?.userInfo?.stats;
                    if (user && user.uniqueId) {
                        return {
                            unique_id: user.uniqueId || '',
                            nickname: user.nickname || '',
                            avatar: user.avatarLarger || user.avatarMedium || '',
                            signature: user.signature || '',
                            follower_count: stats?.followerCount || 0,
                            following_count: stats?.followingCount || 0,
                            likes_count: stats?.heartCount || 0,
                            video_count: stats?.videoCount || 0,
                            verified: user.verified || false,
                            private_account: user.privateAccount || false,
                        };
                    }
                    return { raw: text.substring(0, 500) };
                } catch(e) {
                    return { error: e.toString() };
                }
            }""")
            print(f"[TIKTOK DEBUG] Self-info API: {info3}")
            if info3 and info3.get("unique_id"):
                return info3

        finally:
            await browser.close()

    raise ValueError("Could not fetch TikTok account info. Cookies may be expired.")


# ── Upload via Playwright ───────────────────────────────────────────────────

async def upload_video(
    video_path: str,
    caption: str,
    cookies_json: str,
    *,
    visibility: str = "PUBLIC_TO_EVERYONE",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
) -> dict:
    """Upload a video to TikTok using Playwright browser automation.

    Args:
        video_path: Absolute path to the video file.
        caption: Caption text (max 2200 chars, hashtags work).
        cookies_json: Encrypted cookies JSON string.
        visibility: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR, SELF_ONLY.
        disable_comment: Disable comments on the post.
        disable_duet: Disable duet.
        disable_stitch: Disable stitch.

    Returns:
        dict with keys: ok, video_url (if detectable), publish_id
    """
    from patchright.async_api import async_playwright

    cookies = parse_cookies(cookies_json)
    if not validate_tiktok_cookies(cookies):
        raise ValueError("Invalid TikTok cookies: sessionid not found")

    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    abs_path = str(video_file.resolve())

    logger.info("Starting TikTok upload: %s (%s bytes)", video_file.name, video_file.stat().st_size)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=TIKTOK_HEADERS["User-Agent"],
            viewport={"width": 1280, "height": 800},
        )

        # Inject cookies
        await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            # Navigate to upload page
            await page.goto("https://www.tiktok.com/upload", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            current_url = page.url
            logger.info("TikTok upload page loaded: %s", current_url)

            # Check if logged in by looking for upload form
            upload_input = page.locator('input[type="file"]').first
            is_visible = await upload_input.is_visible(timeout=10000)
            logger.info("Upload input visible: %s", is_visible)
            if not is_visible:
                raise ValueError("Not logged in or upload page not accessible. Cookies may be expired.")

            # Upload video file
            await upload_input.set_input_files(abs_path)

            # Wait for upload to process
            logger.info("Video uploaded, waiting for processing...")
            await page.wait_for_timeout(5000)

            # Wait for the caption box to appear
            caption_box = page.locator('[contenteditable="true"]').first
            for _ in range(30):
                if await caption_box.is_visible(timeout=2000):
                    break
            else:
                raise ValueError("Caption box did not appear after upload")

            # Clear existing text and type caption
            await caption_box.click()
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")
            await caption_box.type(caption, delay=20)
            await page.wait_for_timeout(1000)

            # Click the Post button
            post_btn = page.locator('button:has-text("Post"), button[data-e2e="upload_post"]').first
            if not await post_btn.is_visible(timeout=5000):
                # Try finding by text content
                buttons = await page.locator("button").all()
                for btn in buttons:
                    text = await btn.text_content()
                    if text and "post" in text.lower():
                        post_btn = btn
                        break

            await post_btn.click()
            logger.info("Post button clicked, waiting for confirmation...")

            # Wait for success or redirect
            await page.wait_for_timeout(10000)

            # Try to detect the posted video URL
            current_url = page.url
            video_url = None
            if "/video/" in current_url:
                video_url = current_url

            return {
                "ok": True,
                "video_url": video_url,
                "message": "Video posted successfully",
            }

        except Exception as e:
            logger.error("TikTok upload failed: %s", e)
            return {
                "ok": False,
                "error": str(e),
            }
        finally:
            await browser.close()
