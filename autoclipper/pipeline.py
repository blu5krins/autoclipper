"""End-to-end orchestration: ingest -> transcribe -> analyze -> cut."""
import os
import time

from . import config
from .analyze import find_viral_clips
from .clip import cut_all
from .ingest import ingest
from .reframe import reframe_clip
from .subtitles import add_subtitles
from .transcribe import transcribe
from .utils import ensure_ffmpeg, logger, sanitize_filename, write_json, save_to_library


def _enforce_clip_constraints(clips, min_clip, max_clip, clip_count, video_dur):
    """Adjust Gemini's candidates to respect the user's count and duration window."""
    cleaned = []
    for c in clips:
        try:
            start = float(c.get("start", 0.0))
            end = float(c.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        dur = end - start

        # Trim clips longer than the requested max.
        if max_clip and dur > max_clip:
            end = start + max_clip
            dur = max_clip

        # Pad short clips outward (within video bounds) up to the min duration.
        if min_clip and dur < min_clip:
            need = min_clip - dur
            pad_before = min(start, need / 2.0)
            pad_after = min(max(0.0, video_dur - end), need - pad_before)
            # If we still need more, take the rest from the front.
            if pad_before + pad_after < need:
                pad_before = min(start, need - pad_after)
            start = max(0.0, start - pad_before)
            end = min(video_dur or end, end + pad_after)
            # Final clamp so we never exceed min by padding past video end.
            if video_dur and end - start < min_clip and start > 0:
                start = max(0.0, end - min_clip)

        cleaned.append({**c, "start": round(start, 2), "end": round(end, 2)})

    # Cap the total number of clips at the requested count.
    if clip_count and len(cleaned) > clip_count:
        cleaned = cleaned[:clip_count]

    return cleaned


def run(
    source: str,
    output_dir: str = "output",
    groq_key: str = None,
    gemini_key: str = None,
    whisper_model: str = None,
    gemini_model: str = None,
    vertical: bool = True,
    use_yolo: bool = True,
    subtitles: bool = True,
    force_hd: bool = False,
    cookies_text: str = None,
    clip_count: int = None,
    min_clip: float = None,
    max_clip: float = None,
    content_type: str = None,
) -> dict:
    """Run the full auto-clip pipeline and return a result summary dict."""
    ensure_ffmpeg()
    start_time = time.time()

    os.makedirs(output_dir, exist_ok=True)

    # 1. Ingest
    video_path, title = ingest(source, output_dir, force_hd=force_hd, cookies_text=cookies_text)
    base_name = sanitize_filename(title)

    # 2. Transcribe (Groq Whisper)
    transcript = transcribe(
        video_path, output_dir, api_key=groq_key, model=whisper_model
    )

    # 3. Analyze (Gemini) — language is auto-read from the transcript so that
    # titles / descriptions / hooks are written in the video's own language.
    clip_candidates = find_viral_clips(
        transcript, api_key=gemini_key, model=gemini_model,
        clip_count=clip_count, min_clip=min_clip, max_clip=max_clip,
        content_type=content_type,
    )
    logger.info(
        "Clip params -> requested count=%s min=%s max=%s | Gemini returned %d candidates",
        clip_count, min_clip, max_clip, len(clip_candidates),
    )

    # Enforce the user's duration window and clip count even if Gemini drifts:
    # - pad short clips outward (within video bounds) up to min_clip
    # - trim clips longer than max_clip
    # - cap the total number at clip_count
    video_dur = transcript.get("duration") or 0.0
    if min_clip or max_clip or clip_count:
        clip_candidates = _enforce_clip_constraints(
            clip_candidates, min_clip, max_clip, clip_count, video_dur
        )
        logger.info("After enforcement: %d clip(s)", len(clip_candidates))
    if not clip_candidates:
        logger.warning("No viral clips detected.")

    # 4. Cut clips (FFmpeg)
    clips = cut_all(video_path, clip_candidates, output_dir, base_name)

    # 5. Reframe to vertical 9:16 with face/subject tracking
    if vertical:
        for clip in clips:
            src = os.path.join(output_dir, clip["file"])
            if not os.path.exists(src):
                continue
            v_name = clip["file"].rsplit(".", 1)[0] + "_9x16.mp4"
            v_path = os.path.join(output_dir, v_name)
            if reframe_clip(src, v_path, use_yolo=use_yolo):
                clip["vertical_file"] = v_name
                os.remove(src)
                clip["file"] = v_name

    # 6. Generate subtitle tracks (SRT) for the on-demand "Auto Subtitle" burn.
    #    Clips are NOT burned during generation -- matching OpenShorts, the
    #    burn only happens when the user clicks "Auto Subtitle" on a clip.
    if subtitles:
        add_subtitles(clips, transcript, output_dir, burn=False)

    # 5. Persist metadata
    result = {
        "title": title,
        "source": source,
        "job_id": os.path.basename(output_dir),
        "video_file": os.path.basename(video_path),
        "language": transcript.get("language"),
        "duration": transcript.get("duration"),
        "clips": clips,
        "elapsed_seconds": round(time.time() - start_time, 1),
    }
    metadata_path = os.path.join(output_dir, f"{base_name}_metadata.json")
    write_json(metadata_path, {**result, "transcript": transcript})

    # 6. Save clips into the Saved Library (folder per source video).
    try:
        library_path = save_to_library(output_dir, title, result["job_id"], clips)
        result["library_path"] = os.path.relpath(library_path, output_dir)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not save to library: %s", e)

    logger.info(
        "Done in %.1fs — %d clip(s) written to %s",
        result["elapsed_seconds"],
        len(clips),
        output_dir,
    )
    return result
