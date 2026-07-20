"""Video ingest: download from a URL (yt-dlp) or use a local file."""
import os
import shutil

from . import config
from .utils import logger, sanitize_filename


def _is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def _write_cookies(output_dir: str, cookies_text: str = None):
    """Materialize YouTube cookies (from request or YOUTUBE_COOKIES env) into a
    Netscape cookies file. Returns the path or None if no cookies provided."""
    text = cookies_text or config.YOUTUBE_COOKIES
    if not text or not text.strip():
        return None
    cookies_path = os.path.join(output_dir, "cookies.txt")
    try:
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info("Using YouTube cookies (%d bytes)", os.path.getsize(cookies_path))
        return cookies_path
    except OSError as e:
        logger.warning("Failed to write cookies file: %s", e)
        return None


def _build_youtube_opts(cookies_path, force_hd, use_cookies):
    """Build yt-dlp options.

    - With cookies: try `mweb` first (supports cookies, not subject to SABR like
      `web`). If that still fails the caller falls back to anonymous below.
    - Without cookies: let yt-dlp use its DEFAULT client chain. On this build the
      default resolves to `android_vr` which yields up to 1080p (whereas forcing
      tv_simply/web only gives 360p). We therefore do NOT pin player_client here.
    """
    if use_cookies and cookies_path:
        extractor_args = {"player_client": ["mweb", "web", "tv", "ios", "android_vr", "android"]}
    else:
        # `android`/`android_vr` do not require a PO token and reliably return
        # formats. List several fallbacks so yt-dlp can retry on HTTP 403 / rate
        # limits from YouTube's anti-bot.
        extractor_args = {"player_client": ["android_vr", "android", "tv", "web_safari", "ios"]}
    return _finalize_opts(extractor_args, force_hd, cookies_path if use_cookies else None)
def _finalize_opts(extractor_args, force_hd, cookiefile):
    if force_hd:
        fmt = (
            "bestvideo[height>=720]+bestaudio/"
            "best[height>=720]/best"
        )
    else:
        fmt = (
            "bestvideo+bestaudio/best[ext=mp4]/best"
        )

    last_pct = {"v": -1}

    def _progress(d):
        if d.get("status") == "downloading":
            try:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                got = d.get("downloaded_bytes", 0)
                if total:
                    pct = int(got / total * 100)
                    if pct >= last_pct["v"] + 5:
                        last_pct["v"] = pct
                        logger.info("YouTube download: %d%%", pct)
            except Exception:
                pass

    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": cookiefile,
        "socket_timeout": 30,
        "retries": 10,
        "fragment_retries": 10,
        "nocheckcertificate": True,
        "cachedir": False,
        "format": fmt,
        "merge_output_format": "mp4",
        "progress_hooks": [_progress],
        "extractor_args": {"youtube": extractor_args},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }
    return opts


def _download_youtube(url: str, output_dir: str, force_hd: bool = False, cookies_text: str = None, max_height: int = None):
    import yt_dlp

    cookies_path = _write_cookies(output_dir, cookies_text)
    has_cookies = bool(cookies_path)

    # Try anonymous first: on this build the default client chain (android_vr)
    # yields up to 1080p without needing a PO token. Cookies are used only as a
    # fallback, since logged-in clients (web/mweb) are subject to SABR/PO-token
    # enforcement and often fail in headless environments.
    attempts = [(False, "without cookies (anonymous)")]
    if has_cookies:
        attempts.append((True, "with cookies"))

    last_err = None
    for use_cookies, label in attempts:
        opts = _build_youtube_opts(cookies_path, force_hd, use_cookies)
        if max_height:
            opts["format"] = (
                f"bestvideo[height<={max_height}]+bestaudio/"
                f"best[height<={max_height}]/best"
            )
        try:
            logger.info("YouTube download attempt %s", label)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            title = sanitize_filename(info.get("title", "youtube_video"))
            out_template = os.path.join(output_dir, f"{title}.%(ext)s")
            final_path = os.path.join(output_dir, f"{title}.mp4")
            if os.path.exists(final_path):
                os.remove(final_path)

            download_opts = {**opts, "outtmpl": out_template, "overwrites": True}
            logger.info("Downloading video from YouTube (%s)...", label)
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                ydl.download([url])

            if not os.path.exists(final_path):
                for f in os.listdir(output_dir):
                    if f.startswith(title) and f.endswith(".mp4"):
                        final_path = os.path.join(output_dir, f)
                        break
            if not os.path.exists(final_path):
                raise RuntimeError("yt-dlp finished but no output file was found.")
            logger.info("Downloaded: %s", final_path)
            return final_path, title
        except Exception as e:  # noqa: BLE001
            import traceback

            last_err = e
            logger.warning("YouTube attempt %s failed: %s", label, e)
            logger.warning("Traceback: %s", traceback.format_exc())
            if not has_cookies:
                break

    raise RuntimeError(f"YouTube download failed: {last_err}")


def ingest(source: str, output_dir: str, force_hd: bool = False, cookies_text: str = None, max_height: int = None):
    """Return (video_path, title) for a URL or local file `source`."""
    os.makedirs(output_dir, exist_ok=True)

    if _is_url(source):
        return _download_youtube(source, output_dir, force_hd=force_hd, cookies_text=cookies_text, max_height=max_height)

    if not os.path.exists(source):
        raise FileNotFoundError(f"Input file not found: {source}")

    title = sanitize_filename(os.path.splitext(os.path.basename(source))[0])
    dest = os.path.join(output_dir, f"{title}{os.path.splitext(source)[1] or '.mp4'}")
    if os.path.abspath(source) != os.path.abspath(dest):
        shutil.copy2(source, dest)
    logger.info("Using local file: %s", dest)
    return dest, title
