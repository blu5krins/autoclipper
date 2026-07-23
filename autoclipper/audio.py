"""Audio extraction and chunking for Groq's upload size limit."""
import os
import subprocess

from . import config
from .utils import file_size_mb, logger, probe_duration, run_command


def _has_audio_stream(path: str) -> bool:
    """Return True if the file has at least one audio stream."""
    try:
        out = subprocess.check_output(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', path],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return 'audio' in out
    except Exception:
        return False


def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract a compact 16 kHz mono MP3 (optimal for Whisper) from the video.
    
    If the video has no audio stream, generates silence for the video duration
    so downstream transcription can still proceed (it will produce empty text).
    """
    audio_path = os.path.join(output_dir, "audio.mp3")
    if not _has_audio_stream(video_path):
        duration = probe_duration(video_path)
        logger.warning("No audio stream in %s; generating %.1fs silence", video_path, duration)
        run_command(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono",
                "-t", f"{duration:.3f}",
                "-ac", "1", "-ar", "16000", "-b:a", "64k",
                audio_path,
            ]
        )
    else:
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                audio_path,
            ]
        )
    logger.info("Extracted audio: %s (%.1f MB)", audio_path, file_size_mb(audio_path))
    return audio_path


def split_audio(audio_path: str, output_dir: str, max_mb: float = None):
    """Split audio into <= max_mb chunks.

    Returns a list of (chunk_path, offset_seconds). If the file already fits,
    returns a single entry with offset 0.
    """
    max_mb = max_mb or config.GROQ_MAX_AUDIO_MB
    size_mb = file_size_mb(audio_path)
    if size_mb <= max_mb:
        return [(audio_path, 0.0)]

    duration = probe_duration(audio_path)
    if duration <= 0:
        raise RuntimeError("Could not determine audio duration for chunking.")

    # Pick a chunk length so each chunk stays under the limit (with a margin).
    num_chunks = int(size_mb // max_mb) + 1
    chunk_seconds = duration / num_chunks
    logger.info(
        "Audio %.1f MB exceeds %.0f MB limit; splitting into %d chunks (~%.0fs each)",
        size_mb,
        max_mb,
        num_chunks,
        chunk_seconds,
    )

    chunks = []
    for i in range(num_chunks):
        offset = i * chunk_seconds
        chunk_path = os.path.join(output_dir, f"audio_chunk_{i:03d}.mp3")
        run_command(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{offset:.3f}",
                "-t",
                f"{chunk_seconds:.3f}",
                "-i",
                audio_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                chunk_path,
            ]
        )
        chunks.append((chunk_path, offset))
    return chunks
