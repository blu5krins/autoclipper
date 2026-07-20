"""Voice-over generation (Kokoro TTS locally + Gemini TTS fallback).

Two engines:
  * kokoro  — local, free, no API key. Great for English / multilingual voices.
              Weak for natural Indonesian, so Indonesian text falls back to Gemini.
  * gemini  — cloud TTS via the user's GEMINI_API_KEY. Natural for Indonesian.

The resulting WAV is mixed into a clip via FFmpeg (overlay = mix on top of the
original audio, replace = dub over the original audio).
"""
import base64
import os
import subprocess
import wave

from .utils import logger, run_command

KOKORO_CACHE = os.environ.get("KOKORO_CACHE", os.path.join(os.path.dirname(__file__), "models", "kokoro"))

# A small curated set of Kokoro voices (lang_code -> [voice ids]).
KOKORO_VOICES = {
    "a": ["af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
          "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
          "am_michael", "am_fenrir", "am_puck", "am_zeno"],
    "b": ["bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable",
          "bm_george", "bm_leo", "bm_pete"],
}

# Gemini TTS voices (a few high-quality options; language chosen by voice name).
GEMINI_VOICES = [
    "en-US-Chirp3-HD-Achernar", "en-US-Chirp3-HD-Aoede", "en-US-Chirp3-HD-Autonoe",
    "en-GB-Chirp3-HD-Alnilam", "en-AU-Chirp3-HD-Leda",
    "id-ID-Standard-A", "id-ID-Standard-B", "id-ID-Wavenet-A",
    "ko-KR-Chirp3-HD-Achernar", "ja-JP-Chirp3-HD-Achernar",
]

_KOKORO_PIPELINE = None


def kokoro_voices() -> list:
    out = []
    for lang, voices in KOKORO_VOICES.items():
        out.extend(voices)
    return out


def gemini_voices() -> list:
    return list(GEMINI_VOICES)


def _looks_indonesian(text: str) -> bool:
    """Heuristic: Indonesian uses 'a-z' plus many chars absent in English."""
    if not text:
        return False
    indo_markers = set("bcdfghjklmnpqrstvwxyz")  # subset; real check below
    # Common Indonesian words / affixes.
    import re

    words = re.findall(r"[A-Za-z]+", text.lower())
    indo_words = {
        "yang", "dan", "di", "ke", "dari", "ini", "itu", "dengan", "untuk", "pada",
        "adalah", "akan", "tidak", "bisa", "saya", "kamu", "kita", "mereka", "jika",
        "saat", "oleh", "juga", "sudah", "belum", "lagi", "cara", "video", "ini",
    }
    hits = sum(1 for w in words if w in indo_words)
    # Indonesian uses 'a,i,u,e,o' heavily and rare English-only clusters; simple score.
    return hits >= 2


def pick_engine(text: str, force_engine: str = None) -> str:
    if force_engine in ("kokoro", "gemini"):
        return force_engine
    # Default: Kokoro for English-ish text, Gemini for Indonesian.
    return "gemini" if _looks_indonesian(text) else "kokoro"


def _ensure_kokoro():
    global _KOKORO_PIPELINE
    if _KOKORO_PIPELINE is not None:
        return _KOKORO_PIPELINE
    try:
        from kokoro import KPipeline
    except ImportError:
        raise RuntimeError(
            "Kokoro TTS is not installed. Add 'kokoro' to requirements and rebuild."
        )
    os.makedirs(KOKORO_CACHE, exist_ok=True)
    # lang_code 'a' = American English; Kokoro auto-selects per-voice internally.
    _KOKORO_PIPELINE = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _KOKORO_PIPELINE


def generate_with_kokoro(text: str, out_wav: str, voice: str = "af_heart") -> str:
    """Generate a WAV from text using the local Kokoro model."""
    pipeline = _ensure_kokoro()
    import soundfile as sf

    audio_chunks = []
    for _, _, audio in pipeline(text, voice=voice, speed=1.0, split_pattern=r"\n+"):
        audio_chunks.append(audio)
    if not audio_chunks:
        raise RuntimeError("Kokoro produced no audio.")
    import numpy as np

    full = np.concatenate(audio_chunks, axis=0)
    sf.write(out_wav, full, 24000)
    logger.info("Kokoro TTS wrote %s", out_wav)
    return out_wav


def generate_with_gemini(text: str, out_wav: str, api_key: str, voice: str = "id-ID-Standard-A") -> str:
    """Generate a WAV from text using Gemini TTS (requires an API key)."""
    from google import genai

    if not api_key:
        raise RuntimeError("Gemini API key is required for Gemini TTS (set it in Settings).")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=text,
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": voice}}
            },
        },
    )
    data = response.candidates[0].content.parts[0].inline_data.data
    pcm = base64.b64decode(data)
    # Gemini returns 16-bit PCM mono at 24kHz; wrap as WAV.
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    logger.info("Gemini TTS wrote %s", out_wav)
    return out_wav


def generate_voiceover(
    text: str,
    out_wav: str,
    engine: str = "auto",
    voice: str = None,
    gemini_key: str = None,
) -> str:
    """Pick an engine and generate the voice-over WAV. Returns the wav path."""
    engine = pick_engine(text, engine)
    if engine == "kokoro":
        voice = voice or "af_heart"
        try:
            return generate_with_kokoro(text, out_wav, voice)
        except Exception as e:  # noqa: BLE001
            # If Kokoro fails and we have a Gemini key, fall back transparently.
            if gemini_key:
                logger.warning("Kokoro failed (%s); falling back to Gemini TTS.", e)
                return generate_with_gemini(text, out_wav, gemini_key, voice or "en-US-Chirp3-HD-Aoede")
            raise
    else:
        voice = voice or "id-ID-Standard-A"
        return generate_with_gemini(text, out_wav, gemini_key, voice)


def mix_voiceover(video_in: str, wav_in: str, video_out: str, mode: str = "overlay") -> str:
    """Mix the voice-over WAV into the video.

    mode='overlay' -> keep original audio (reduced) and layer VO on top.
    mode='replace' -> discard original audio, use VO only (full dub).
    """
    if mode == "replace":
        cmd = [
            "ffmpeg", "-y", "-i", video_in, "-i", wav_in,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            video_out,
        ]
    else:  # overlay
        cmd = [
            "ffmpeg", "-y", "-i", video_in, "-i", wav_in,
            "-filter_complex",
            "[0:a]volume=0.35[a0];[1:a]volume=1.0[a1];"
            "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
            video_out,
        ]
    run_command(cmd)
    logger.info("Mixed voice-over into %s (mode=%s)", video_out, mode)
    return video_out
