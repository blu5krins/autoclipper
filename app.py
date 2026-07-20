"""AutoClipper FastAPI server with an async job queue.

Endpoints:
    POST /api/process        -> submit a video (YouTube URL or local path); returns job_id
    GET  /api/status/{id}    -> poll job status, logs, and result
    GET  /api/jobs           -> list recent jobs
    GET  /api/files/{id}/{f} -> download a generated clip / asset

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
"""
import asyncio
import contextvars
import json
import logging
import os
from typing import Optional
import shutil
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from autoclipper import config, pipeline
from autoclipper.trending import get_trending_ideas
from autoclipper.trending_youtube import fetch_trending, enrich_trending, CATEGORY_MAP
from autoclipper.subtitles import build_ass, burn_ass
from autoclipper.hooks import add_hook_to_video
from autoclipper.youtube_uploader import (
    get_auth_url,
    exchange_code,
    is_authenticated,
    upload_video,
    has_client_secret,
)
from autoclipper.utils import ensure_ffmpeg, logger as ac_logger, sanitize_filename, write_json

app = FastAPI(title="AutoClipper API", version="0.1.0")


# --- Output cleanup -------------------------------------------------------
# Job folders under OUTPUT_ROOT accumulate fast (each job keeps source video,
# every generated clip, vertical re-encodes, subtitles, hooks...). A background
# task prunes folders older than JOB_RETENTION_HOURS so disk doesn't fill up.
# Folders that were saved into the Library are preserved.
JOB_RETENTION_HOURS = float(os.environ.get("JOB_RETENTION_HOURS", "24"))
_CLEANUP_INTERVAL = 60 * 30  # seconds between sweeps


def _is_library_folder(name: str) -> bool:
    """Library folders are keyed by sanitized video title, not a 12-hex job id."""
    manifest = os.path.join(config.OUTPUT_ROOT, name, f"{name}_library.json")
    return os.path.isfile(manifest)


def _sweep_old_jobs() -> int:
    """Delete job folders (not library folders) older than the retention window."""
    if not os.path.isdir(config.OUTPUT_ROOT):
        return 0
    # Never touch these shared/persistent folders.
    protected = {"library", "uploads", "models"}
    cutoff = time.time() - JOB_RETENTION_HOURS * 3600
    removed = 0
    for name in os.listdir(config.OUTPUT_ROOT):
        if name in protected:
            continue
        path = os.path.join(config.OUTPUT_ROOT, name)
        if not os.path.isdir(path):
            continue
        if _is_library_folder(name):
            continue  # keep saved library folders
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed


async def _cleanup_loop():
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        try:
            n = await asyncio.to_thread(_sweep_old_jobs)
            if n:
                logger.info("Cleanup: removed %d old job folder(s) (>%.0fh).", n, JOB_RETENTION_HOURS)
        except Exception as e:  # noqa: BLE001
            logger.warning("Cleanup sweep failed: %s", e)


@app.on_event("startup")
async def _startup_cleanup():
    asyncio.create_task(_cleanup_loop())


@app.post("/api/cleanup")
async def manual_cleanup(request: Request, hours: float = None):
    """Force a cleanup sweep. Optional `hours` override (query or JSON body)."""
    global JOB_RETENTION_HOURS
    override = hours
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("hours") is not None:
            override = float(body["hours"])
    except Exception:
        pass
    saved = JOB_RETENTION_HOURS
    if override is not None:
        JOB_RETENTION_HOURS = max(0.0, override)
    try:
        removed = await asyncio.to_thread(_sweep_old_jobs)
    finally:
        JOB_RETENTION_HOURS = saved
    return {"ok": True, "removed": removed, "retention_hours": override or saved}


# --- Per-job state --------------------------------------------------------
_current_job_id = contextvars.ContextVar("current_job_id", default=None)
jobs: dict[str, dict] = {}
_semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_JOBS)


class JobLogHandler(logging.Handler):
    """Route autoclipper log records to the active job's log buffer."""

    def emit(self, record: logging.LogRecord):
        jid = _current_job_id.get()
        job = jobs.get(jid) if jid else None
        if job is None:
            return
        job["logs"].append(self.format(record))


ac_logger.addHandler(JobLogHandler())
ac_logger.setLevel(logging.INFO)


# --- Request models -------------------------------------------------------
class SubtitleRequest(BaseModel):
    job_id: str
    filename: str
    cues: list  # [{"start": float, "end": float, "text": str}]
    style: dict = {}


# --- Job runner -----------------------------------------------------------
def _run_pipeline_sync(job_id: str, source: str, output_dir: str, opts: dict):
    _current_job_id.set(job_id)
    return pipeline.run(source, output_dir=output_dir, **opts)


async def _run_job(job_id: str, source: str, opts: dict):
    job = jobs[job_id]
    output_dir = os.path.join(config.OUTPUT_ROOT, job_id)
    try:
        async with _semaphore:
            job["status"] = "processing"
            result = await asyncio.to_thread(
                _run_pipeline_sync, job_id, source, output_dir, opts
            )
        job["result"] = result
        job["status"] = "completed"
    except Exception as e:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(e)
    finally:
        job["finished_at"] = time.time()


# --- Routes ---------------------------------------------------------------
@app.get("/")
async def root():
    return {"name": "AutoClipper API", "version": "0.1.0", "jobs": len(jobs)}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a raw file and return its server-side filename (in uploads/)."""
    uploads = os.path.join(config.OUTPUT_ROOT, "uploads")
    os.makedirs(uploads, exist_ok=True)
    original = file.filename or "upload.mp4"
    ext = os.path.splitext(original)[1] or ".mp4"
    name = f"{uuid.uuid4().hex[:8]}_{sanitize_filename(os.path.splitext(original)[0])}{ext}"
    path = os.path.join(uploads, name)
    with open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    return {"filename": name, "path": path}


@app.post("/api/process")
async def process(
    source: str = Form(""),
    file: UploadFile = File(None),
    whisper_model: str = Form(None),
    gemini_model: str = Form(None),
    vertical: bool = Form(True),
    use_yolo: bool = Form(True),
    subtitles: bool = Form(True),
    force_hd: bool = Form(False),
    youtube_cookies: str = Form(None),
    groq_key: str = Form(None),
    gemini_key: str = Form(None),
    clip_count: int = Form(None),
    min_clip: float = Form(None),
    max_clip: float = Form(None),
    content_type: str = Form("general"),
):
    ensure_ffmpeg()

    # Single-step upload: stream the posted file straight into the pipeline.
    if file is not None:
        uploads = os.path.join(config.OUTPUT_ROOT, "uploads")
        os.makedirs(uploads, exist_ok=True)
        original = file.filename or "upload.mp4"
        ext = os.path.splitext(original)[1] or ".mp4"
        name = f"{uuid.uuid4().hex[:8]}_{sanitize_filename(os.path.splitext(original)[0])}{ext}"
        path = os.path.join(uploads, name)
        with open(path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        source = path

    if not source or not source.strip():
        raise HTTPException(status_code=400, detail="Provide a 'source' URL/path or upload a 'file'.")

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "source": source,
        "created_at": time.time(),
        "finished_at": None,
        "logs": [],
        "result": None,
        "error": None,
    }
    opts = {
        "whisper_model": whisper_model,
        "gemini_model": gemini_model,
        "vertical": vertical,
        "use_yolo": use_yolo,
        "subtitles": subtitles,
        "force_hd": force_hd,
        "cookies_text": youtube_cookies,
        "groq_key": groq_key,
        "gemini_key": gemini_key,
        "clip_count": clip_count,
        "min_clip": min_clip,
        "max_clip": max_clip,
        "content_type": content_type or "general",
    }
    if (
        opts["min_clip"] is not None
        and opts["max_clip"] is not None
        and opts["min_clip"] > opts["max_clip"]
    ):
        opts["min_clip"], opts["max_clip"] = opts["max_clip"], opts["min_clip"]
    asyncio.create_task(_run_job(job_id, source, opts))
    return {"job_id": job_id, "status": "queued"}


class GamingPrepareRequest(BaseModel):
    source: str = ""          # path/URL already on server, or empty if file uploaded
    cam_box: dict            # normalized {x,y,w,h} 0..1
    game_box: dict           # normalized {x,y,w,h} 0..1
    layout: str = "cam_top"  # cam_top | game_top | side
    file: str = None         # optional server-side uploaded filename (in uploads/)


@app.post("/api/gaming/prepare")
async def gaming_prepare(req: GamingPrepareRequest):
    """Compose a 9:16 gaming video from two regions of a single source.

    Runs as an async job (returns a `job_id` immediately); poll /api/status/{job_id}.
    When finished, `result.source` is the gaming_layout.mp4 path and
    `result.preview_url` can be used as the `source` for /api/process.
    """
    from autoclipper import gaming_layout
    from autoclipper import ingest as ingest_mod

    source = req.source
    if not source and req.file:
        source = os.path.join(config.OUTPUT_ROOT, "uploads", req.file)

    if not source:
        raise HTTPException(status_code=400, detail="Provide a valid 'source' URL or uploaded 'file'.")

    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "source": source,
        "created_at": time.time(),
        "finished_at": None,
        "logs": ["Queued gaming layout job…"],
        "result": None,
        "error": None,
    }
    asyncio.create_task(asyncio.to_thread(_run_gaming_job, job_id, source, req))
    return {"job_id": job_id, "status": "queued"}


def _run_gaming_job(job_id: str, source: str, req: GamingPrepareRequest):
    from autoclipper import gaming_layout
    from autoclipper import ingest as ingest_mod

    job = jobs[job_id]
    try:
        job["status"] = "downloading"
        # If the source is a YouTube (or other remote) URL, download it first.
        if not os.path.isfile(source) and ingest_mod._is_url(source):
            dl_dir = os.path.join(config.OUTPUT_ROOT, job_id)
            os.makedirs(dl_dir, exist_ok=True)
            job["logs"].append("Downloading source from URL…")
            source, _ = ingest_mod.ingest(
                source, dl_dir, force_hd=False, cookies_text=config.YOUTUBE_COOKIES, max_height=720
            )

        if not os.path.isfile(source):
            raise RuntimeError("Source file not found after download.")

        out_dir = os.path.join(config.OUTPUT_ROOT, job_id)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "gaming_layout.mp4")

        job["status"] = "processing"
        job["logs"].append("Building 9:16 gaming layout…")
        gaming_layout.build_gaming_video(
            source, req.cam_box, req.game_box,
            layout=req.layout, out_path=out_path,
        )

        job["status"] = "done"
        job["finished_at"] = time.time()
        job["result"] = {
            "source": out_path,
            "layout": req.layout,
            "preview_url": f"/api/files/{job_id}/gaming_layout.mp4",
        }
        job["logs"].append("Gaming layout ready.")
    except Exception as e:  # noqa: BLE001
        logger.exception("Gaming layout failed")
        job["status"] = "error"
        job["error"] = str(e)
        job["finished_at"] = time.time()
        job["logs"].append(f"Error: {e}")


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "source": job["source"],
        "created_at": job["created_at"],
        "finished_at": job["finished_at"],
        "logs": job["logs"],
        "result": job["result"],
        "error": job["error"],
    }


@app.get("/api/jobs")
async def list_jobs():
    return [
        {
            "job_id": j["job_id"],
            "status": j["status"],
            "source": j["source"],
            "created_at": j["created_at"],
            "clips": [c.get("file") for c in (j["result"] or {}).get("clips", [])],
        }
        for j in sorted(jobs.values(), key=lambda x: x["created_at"], reverse=True)
    ]


@app.get("/api/files/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    path = os.path.join(config.OUTPUT_ROOT, job_id, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/api/trending")
async def trending(niche: str = "general", count: int = 10,
                   gemini_key: str = None, gemini_model: str = None):
    """Return AI-generated trending short-video ideas for a niche."""
    try:
        ideas = get_trending_ideas(
            niche=niche, api_key=gemini_key, model=gemini_model, count=count
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {"niche": niche, "count": len(ideas), "ideas": ideas}


@app.get("/api/trending/youtube")
async def trending_youtube(
    region: str = "ID",
    category: str = "general",
    max_results: int = 12,
    window_days: int = 3,
    youtube_key: str = None,
    gemini_key: str = None,
    gemini_model: str = None,
    enrich: bool = True,
):
    """Return Explore-style most-popular YouTube videos for a region/category.

    YouTube retired the Trending page in July 2025 in favor of Explore
    (per-category destination pages). This mirrors that by pulling
    videos.list chart=mostPopular for the region and filtering by the
    chosen Explore category (Music, Gaming, News, ...). Shorts are
    filtered out; podcast mode keeps only longer talk videos.
    `category` is one of the EXPLORE_CATEGORIES ids.
    """
    api_key = youtube_key or config.YOUTUBE_API_KEY
    try:
        videos = fetch_trending(
            api_key=api_key, region=region, category=category,
            max_results=max(1, min(max_results or 12, 25)),
            window_days=max(1, min(window_days or 3, 7)),
        )
        # Fallback: if a niche filter yields nothing (YouTube's per-region
        # trending often lacks that category), return the general list and
        # flag it so the UI can show a hint.
        category_filtered = True
        if not videos and category != "general":
            videos = fetch_trending(
                api_key=api_key, region=region, category="general",
                max_results=max(1, min(max_results or 12, 25)),
                window_days=max(1, min(window_days or 3, 7)),
            )
            category_filtered = False
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))

    insights = {}
    if enrich:
        try:
            insights = enrich_trending(
                videos, niche=category, api_key=gemini_key, model=gemini_model
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Trending enrichment skipped: %s", e)
    for v in videos:
        v["idea"] = insights.get(v["video_id"], "")
    return {"region": region, "category": category,
            "category_label": CATEGORY_MAP.get(category, ("0", category))[1],
            "category_filtered": category_filtered,
            "count": len(videos), "videos": videos}


def trending_youtube_category(category: str) -> str:
    from autoclipper.trending_youtube import CATEGORY_MAP

    return CATEGORY_MAP.get(category, ("0", "Explore"))[0]


@app.post("/api/subtitle")
async def subtitle(req: SubtitleRequest):
    output_dir = os.path.join(config.OUTPUT_ROOT, req.job_id)
    video = os.path.join(output_dir, req.filename)
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail="Clip not found")

    base = os.path.splitext(req.filename)[0]
    ass_path = os.path.join(output_dir, f"{base}_edit.ass")
    out_name = f"{base}_edited.mp4"
    out_path = os.path.join(output_dir, out_name)

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(build_ass(req.cues, req.style))

    try:
        burn_ass(video, ass_path, out_path)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"Burn failed: {e}")

    return {"filename": out_name}


class HookRequest(BaseModel):
    job_id: str
    filename: str
    text: str
    position: str = "top"  # top | center | bottom
    font_scale: float = 1.0
    size: str = "M"  # S | M | L
    entrance: str = "fade"  # fade | none
    hold_seconds: float = 5.0


@app.post("/api/hook")
async def hook(req: HookRequest):
    """Burn a viral hook text overlay onto a generated clip (OpenShorts-style)."""
    output_dir = os.path.join(config.OUTPUT_ROOT, req.job_id)
    video = os.path.join(output_dir, req.filename)
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail="Clip not found")
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Hook text is required")

    base = os.path.splitext(req.filename)[0]
    out_name = f"hook_{base}.mp4"
    out_path = os.path.join(output_dir, out_name)

    try:
        add_hook_to_video(
            video, req.text, out_path,
            position=req.position, font_scale=req.font_scale,
            size=req.size, entrance=req.entrance, hold_seconds=req.hold_seconds,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hook failed: {e}")

    return {"filename": out_name}


class HookPreviewRequest(BaseModel):
    job_id: str
    filename: str
    text: str
    position: str = "top"
    font_scale: float = 1.0
    size: str = "M"


@app.post("/api/hook/preview")
async def hook_preview(req: HookPreviewRequest):
    """Render a single preview frame (PNG) with the hook overlay, for the UI."""
    from autoclipper import hooks as _hooks

    output_dir = os.path.join(config.OUTPUT_ROOT, req.job_id)
    video = os.path.join(output_dir, req.filename)
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail="Clip not found")
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Hook text is required")

    size_scale = {"S": 0.7, "L": 1.4}.get((req.size or "M").upper(), 1.0)
    font_scale = req.font_scale * size_scale

    preview_name = f"hook_preview_{os.path.splitext(req.filename)[0]}.png"
    preview_path = os.path.join(output_dir, preview_name)
    try:
        _hooks.create_hook_image(
            req.text, int(1080 * 0.9), preview_path, font_scale=font_scale
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")

    return FileResponse(preview_path, media_type="image/png",
                        filename=preview_name)


# --- Saved Library -------------------------------------------------------
LIBRARY_ROOT = os.path.join(config.OUTPUT_ROOT, "library")


@app.get("/api/library")
async def list_library():
    if not os.path.isdir(LIBRARY_ROOT):
        return []
    items = []
    for name in sorted(os.listdir(LIBRARY_ROOT)):
        folder = os.path.join(LIBRARY_ROOT, name)
        if not os.path.isdir(folder):
            continue
        manifest_path = os.path.join(folder, "manifest.json")
        manifest = {}
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except (OSError, json.JSONDecodeError):
                manifest = {}
        clips = []
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith(".mp4"):
                clips.append(fn)
        if not clips:
            continue
        items.append(
            {
                "name": name,
                "title": manifest.get("title", name),
                "clips": [
                    {
                        "file": fn,
                        "index": int("".join(filter(str.isdigit, fn)) or "0"),
                        "title": _clip_meta(manifest, fn, i),
                        "description": _clip_desc(manifest, fn, i),
                        "hook": _clip_hook(manifest, fn, i),
                    }
                    for i, fn in enumerate(clips)
                ],
            }
        )
    return items


@app.get("/api/library/{name}/{filename}")
async def library_file(name: str, filename: str):
    path = os.path.join(LIBRARY_ROOT, name, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.delete("/api/library/{name}/{filename}")
async def delete_library_clip(name: str, filename: str):
    """Delete a single clip (and its SRT) from a library folder."""
    folder = os.path.join(LIBRARY_ROOT, name)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=404, detail="Library folder not found")
    removed = []
    import re
    srt_name = re.sub(r"\.mp4$", ".srt", filename, flags=re.IGNORECASE)
    for fn in (filename, srt_name):
        p = os.path.join(folder, fn)
        if os.path.isfile(p):
            try:
                os.remove(p)
                removed.append(fn)
            except OSError as e:
                raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    # Drop the clip from the manifest.
    manifest_path = os.path.join(folder, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["clips"] = [
                c for c in manifest.get("clips", []) if c.get("file") != filename
            ]
            write_json(manifest_path, manifest)
        except (OSError, json.JSONDecodeError):
            pass
    # If no clips remain, remove the whole folder.
    remaining = [f for f in os.listdir(folder) if f.lower().endswith(".mp4")]
    if not remaining:
        shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "removed": removed}


@app.delete("/api/library/{name}")
async def delete_library_folder(name: str):
    """Delete an entire library folder (all clips for one source video)."""
    folder = os.path.join(LIBRARY_ROOT, name)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=404, detail="Library folder not found")
    shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "removed": name}


# --- YouTube Shorts upload (free, YouTube Data API v3) -------------------
class YouTubeAuthRequest(BaseModel):
    redirect_uri: str = None


class YouTubeUploadRequest(BaseModel):
    job_id: Optional[str] = None    # for generated clips
    name: Optional[str] = None      # for library clips
    filename: str
    title: str = ""
    description: str = ""
    publish_at: Optional[str] = None  # ISO 8601; if set -> scheduled (private until then)
    thumbnail: Optional[str] = None


@app.get("/api/youtube/status")
async def youtube_status():
    return {
        "configured": has_client_secret(),
        "authenticated": is_authenticated(),
    }


@app.post("/api/youtube/auth_url")
async def youtube_auth_url(req: YouTubeAuthRequest):
    if not has_client_secret():
        raise HTTPException(
            status_code=400,
            detail="YouTube client_secret.json not configured on the server.",
        )
    url = get_auth_url(req.redirect_uri)
    if not url:
        raise HTTPException(status_code=500, detail="Failed to build auth URL")
    return {"auth_url": url}


@app.post("/api/youtube/callback")
async def youtube_callback(code: str, redirect_uri: str = None):
    ok = exchange_code(code, redirect_uri)
    if not ok:
        raise HTTPException(status_code=400, detail="Token exchange failed")
    return {"ok": True, "authenticated": is_authenticated()}


@app.post("/api/youtube/upload")
async def youtube_upload(req: YouTubeUploadRequest):
    if not is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated with YouTube")

    # Resolve the source video file.
    if req.name:
        video = os.path.join(config.OUTPUT_ROOT, "library", req.name, req.filename)
    else:
        if not req.job_id:
            raise HTTPException(status_code=400, detail="job_id or name required")
        video = os.path.join(config.OUTPUT_ROOT, req.job_id, req.filename)
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail="Clip not found")

    thumb = None
    if req.thumbnail:
        if req.name:
            thumb = os.path.join(config.OUTPUT_ROOT, "library", req.name, req.thumbnail)
        else:
            thumb = os.path.join(config.OUTPUT_ROOT, req.job_id, req.thumbnail)
        if not os.path.isfile(thumb):
            thumb = None

    try:
        result = upload_video(
            video,
            title=req.title,
            description=req.description,
            publish_at=req.publish_at,
            thumbnail_path=thumb,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        detail = f"YouTube upload failed: {e}"
        # Try to extract a readable YouTube API error.
        content = getattr(e, "content", None)
        if content:
            try:
                err = json.loads(content.decode("utf-8"))
                reasons = [
                    f"{x.get('reason', '')}: {x.get('message', '')}"
                    for x in err.get("error", {}).get("errors", [])
                ]
                if reasons:
                    detail = "; ".join(reasons)
            except (ValueError, AttributeError):
                pass
        else:
            detail = f"{type(e).__name__}: {str(e)[:300]}"
        raise HTTPException(status_code=500, detail=detail)

    video_id = result.get("id")
    return {
        "ok": True,
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}" if video_id else None,
        "scheduled": bool(req.publish_at),
        "publish_at": req.publish_at,
    }


class SaveLibraryRequest(BaseModel):
    job_id: str
    filename: str
    title: str = None
    clip_title: str = None
    description: str = None
    hook: str = None


@app.post("/api/library/save")
async def save_to_library_endpoint(req: SaveLibraryRequest):
    """Copy a generated clip into the Saved Library (one clip at a time)."""
    src = os.path.join(config.OUTPUT_ROOT, req.job_id, req.filename)
    if not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="Clip not found")

    safe_title = sanitize_filename(req.title or f"video_{req.job_id}")
    lib_root = LIBRARY_ROOT
    base = os.path.join(lib_root, safe_title)
    n = 1
    while os.path.exists(base):
        # If folder exists, reuse it; otherwise avoid collisions.
        base = os.path.join(lib_root, f"{safe_title}_{n}")
        n += 1
    os.makedirs(base, exist_ok=True)

    # Determine the next clip index in this folder.
    existing = [f for f in os.listdir(base) if f.lower().endswith(".mp4")]
    idx = len(existing) + 1
    dest = os.path.join(base, f"clip{idx}.mp4")
    try:
        shutil.copy2(src, dest)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Copy failed: {e}")

    # Copy the accompanying SRT (if present) so subtitles can be re-burned later.
    srt_src = os.path.splitext(src)[0] + ".srt"
    if os.path.isfile(srt_src):
        try:
            shutil.copy2(srt_src, os.path.splitext(dest)[0] + ".srt")
        except OSError:
            pass

    # Update / create the manifest.
    manifest_path = os.path.join(base, "manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError):
            manifest = {}
    manifest.setdefault("title", req.title or safe_title)
    manifest.setdefault("job_id", req.job_id)
    clips = manifest.get("clips", [])
    clips.append(
        {
            "index": idx,
            "title": req.clip_title or req.filename,
            "description": req.description or "",
            "hook": req.hook or "",
        }
    )
    manifest["clips"] = clips
    write_json(manifest_path, manifest)

    rel = os.path.relpath(base, config.OUTPUT_ROOT)
    return {"library": rel, "folder": os.path.basename(base), "file": f"clip{idx}.mp4"}


class RegisterBurnRequest(BaseModel):
    name: str
    source_file: str
    result_file: str


@app.post("/api/library/register")
async def register_burn(req: RegisterBurnRequest):
    """Record a burned (subtitled) clip into the library folder's manifest."""
    base = os.path.join(LIBRARY_ROOT, req.name)
    if not os.path.isdir(base):
        raise HTTPException(status_code=404, detail="Library folder not found")
    if not os.path.isfile(os.path.join(base, req.result_file)):
        raise HTTPException(status_code=404, detail="Burned file not found")

    manifest_path = os.path.join(base, "manifest.json")
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError):
            manifest = {}

    src_idx = int("".join(filter(str.isdigit, req.source_file)) or "0")
    for c in manifest.get("clips", []):
        if c.get("index") == src_idx:
            c["subtitled"] = req.result_file
            c["subtitled_title"] = req.result_file
            break
    else:
        clips = manifest.setdefault("clips", [])
        clips.append(
            {
                "index": src_idx,
                "title": req.source_file,
                "subtitled": req.result_file,
            }
        )
    write_json(manifest_path, manifest)
    return {"ok": True, "file": req.result_file}


def _clip_field(manifest: dict, filename: str, key: str, position: int = 0) -> str:
    for c in manifest.get("clips", []):
        if c.get("file") == filename:
            return c.get(key, "")
    # Fallback: match by extracted index (for older manifests).
    idx = int("".join(filter(str.isdigit, filename)) or "0")
    for c in manifest.get("clips", []):
        if c.get("index") == idx:
            return c.get(key, "")
    # Last resort: positional match (older manifests with mismatched indices).
    clips = manifest.get("clips", [])
    if 0 <= position < len(clips):
        return clips[position].get(key, "")
    return ""


def _clip_meta(manifest: dict, filename: str, position: int = 0) -> str:
    return _clip_field(manifest, filename, "title", position)


def _clip_desc(manifest: dict, filename: str, position: int = 0) -> str:
    return _clip_field(manifest, filename, "description", position)


def _clip_hook(manifest: dict, filename: str, position: int = 0) -> str:
    return _clip_field(manifest, filename, "hook", position)
