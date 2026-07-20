"""Cut clips from the source video with FFmpeg."""
import os

from .utils import logger, run_command


def cut_clip(video_path: str, start: float, end: float, out_path: str) -> str:
    """Extract [start, end] as an H.264/AAC MP4 (frame-accurate re-encode)."""
    duration = max(0.1, end - start)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            video_path,
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-x264-params",
            "ref=4:me=hex:subme=7:trellis=1",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            out_path,
        ]
    )
    return out_path


def cut_all(video_path: str, clips: list, output_dir: str, base_name: str) -> list:
    """Cut every clip; returns the clips list enriched with 'file' paths."""
    results = []
    for i, clip in enumerate(clips, start=1):
        out_name = f"{base_name}_clip_{i}.mp4"
        out_path = os.path.join(output_dir, out_name)
        logger.info(
            "Cutting clip %d/%d [%.1f-%.1f]: %s",
            i,
            len(clips),
            clip["start"],
            clip["end"],
            clip.get("title", ""),
        )
        try:
            cut_clip(video_path, clip["start"], clip["end"], out_path)
            enriched = {**clip, "index": i, "file": out_name}
            results.append(enriched)
        except RuntimeError as e:
            logger.error("Failed to cut clip %d: %s", i, e)
    return results
