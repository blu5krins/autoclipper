"""Transcription via Groq's OpenAI-compatible Whisper endpoint."""
import os

import httpx

from . import config
from .audio import extract_audio, split_audio
from .utils import logger


def _transcribe_file(audio_path: str, api_key: str, model: str) -> dict:
    """Transcribe a single audio file with word + segment timestamps."""
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
        data = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                config.GROQ_TRANSCRIBE_URL,
                headers=headers,
                data=data,
                files=files,
            )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq transcription failed ({resp.status_code}): {resp.text}")
    return resp.json()


def _offset_items(items, offset: float, keys=("start", "end")):
    for item in items or []:
        for k in keys:
            if k in item and item[k] is not None:
                item[k] = round(item[k] + offset, 3)
    return items or []


def transcribe(video_path: str, output_dir: str, api_key: str = None, model: str = None) -> dict:
    """Transcribe a video's audio, handling Groq's file-size limit via chunking.

    Returns a normalized dict:
        {
          "language": str,
          "duration": float,
          "text": str,
          "words":    [{"word", "start", "end"}, ...],
          "segments": [{"start", "end", "text"}, ...],
        }
    """
    api_key = config.require(api_key or config.GROQ_API_KEY, "GROQ_API_KEY")
    model = model or config.GROQ_WHISPER_MODEL

    logger.info("Transcribing with Groq model '%s'...", model)
    audio_path = extract_audio(video_path, output_dir)
    chunks = split_audio(audio_path, output_dir)

    all_words, all_segments = [], []
    full_text_parts = []
    language = None

    for idx, (chunk_path, offset) in enumerate(chunks):
        logger.info("Transcribing chunk %d/%d (offset %.1fs)", idx + 1, len(chunks), offset)
        result = _transcribe_file(chunk_path, api_key, model)
        language = language or result.get("language")
        full_text_parts.append((result.get("text") or "").strip())
        all_words.extend(_offset_items(result.get("words"), offset))
        all_segments.extend(
            _offset_items(
                [
                    {"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "").strip()}
                    for s in result.get("segments", [])
                ],
                offset,
            )
        )

    transcript = {
        "language": language,
        "duration": all_segments[-1]["end"] if all_segments else 0.0,
        "text": " ".join(p for p in full_text_parts if p),
        "words": all_words,
        "segments": all_segments,
    }
    logger.info(
        "Transcription complete: %d words, %d segments", len(all_words), len(all_segments)
    )
    return transcript
