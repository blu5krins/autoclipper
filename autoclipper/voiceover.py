"""Voice-over generation (Kokoro local + Edge TTS + Gemini cloud).

Engines:
  * kokoro  — local, free, no API key. DEFAULT for all text (no quota limits).
  * edge    — Microsoft Edge TTS (free, no API key, Indonesian voices available).
  * gemini  — cloud TTS via the user's GEMINI_API_KEY. Opt-in (engine="gemini");
              more natural for Indonesian but subject to free-tier quota.

The resulting WAV is mixed into a clip via FFmpeg (overlay = mix on top of the
original audio, replace = dub over the original audio).
"""
import asyncio
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

# Gemini TTS voices (valid Chirp3-HD voices; Gemini TTS has no id-ID voices,
# these multilingual/English voices still synthesize Bahasa Indonesia naturally).
GEMINI_VOICES = [
    "achernar", "aoede", "autonoe", "alnilam", "leda",
    "schedar", "umbriel", "vindemiatrix", "puck", "zephyr",
]

# Edge TTS voices (Indonesian + common multilingual).
EDGE_VOICES = [
    "id-ID-GadisNeural", "id-ID-ArdiNeural",
    "en-US-JennyNeural", "en-US-GuyNeural",
    "en-GB-SoniaNeural", "en-GB-RyanNeural",
    "ja-JP-NanamiNeural", "ko-KR-SunHiNeural",
    "zh-CN-XiaoxiaoNeural",
]

_KOKORO_PIPELINE = None


def kokoro_voices() -> list:
    out = []
    for lang, voices in KOKORO_VOICES.items():
        out.extend(voices)
    return out


def gemini_voices() -> list:
    return list(GEMINI_VOICES)


def edge_voices() -> list:
    return list(EDGE_VOICES)


def generate_with_edge(text: str, out_wav: str, voice: str = "id-ID-GadisNeural") -> str:
    """Generate a WAV using Microsoft Edge TTS (free, no API key).

    Uses the edge-tts Python API. Outputs MP3, then converts to WAV with ffmpeg.
    """
    import edge_tts as _edge
    import concurrent.futures

    tmp_mp3 = out_wav + ".tmp.mp3"

    async def _gen():
        communicate = _edge.Communicate(text, voice)
        await communicate.save(tmp_mp3)

    def _run_async():
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Already inside an event loop (e.g. FastAPI) — run in a thread.
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pool.submit(asyncio.run, _gen()).result()
        else:
            asyncio.run(_gen())

    _run_async()

    subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_mp3, "-acodec", "pcm_s16le",
         "-ar", "24000", "-ac", "1", out_wav],
        check=True, capture_output=True, text=True,
    )
    os.remove(tmp_mp3)
    logger.info("Edge TTS wrote %s (voice=%s)", out_wav, voice)
    return out_wav


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
    if force_engine in ("kokoro", "gemini", "edge"):
        return force_engine
    # Default to the local Kokoro engine (free, no quota). Gemini is opt-in
    # via engine="gemini" for users who have quota / want more natural Indonesian.
    return "kokoro"


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
    # lang_code 'a' = auto (American English); Kokoro selects per-voice internally.
    # The model is downloaded automatically into KOKORO_CACHE on first use.
    _KOKORO_PIPELINE = KPipeline(lang_code="a")
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


def generate_with_gemini(text: str, out_wav: str, api_key: str, voice: str = "achernar") -> str:
    """Generate a WAV from text using Gemini TTS (requires an API key)."""
    from google import genai

    if not api_key:
        raise RuntimeError("Gemini API key is required for Gemini TTS (set it in Settings).")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.1-flash-tts-preview",
        contents=text,
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": voice}}
            },
        },
    )
    data = response.candidates[0].content.parts[0].inline_data.data
    # The google-genai SDK already returns raw PCM bytes (not base64).
    pcm = data if isinstance(data, (bytes, bytearray)) else base64.b64decode(data)
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
            logger.warning("Kokoro failed (%s); falling back to Gemini TTS.", e)
            return generate_with_gemini(text, out_wav, gemini_key or "", voice or "achernar")
    elif engine == "edge":
        voice = voice or "id-ID-GadisNeural"
        return generate_with_edge(text, out_wav, voice)
    else:
        voice = voice or "achernar"
        try:
            return generate_with_gemini(text, out_wav, gemini_key, voice)
        except Exception as e:  # noqa: BLE001
            err_msg = str(e).lower()
            if "429" in err_msg or "quota" in err_msg or "resource_exhausted" in err_msg:
                logger.warning("Gemini TTS quota exhausted (%s); falling back to Kokoro.", e)
                voice = voice or "af_heart"
                return generate_with_kokoro(text, out_wav, voice)
            raise


def wav_duration(wav_in: str) -> float:
    """Return the duration (seconds) of an audio file (any format)."""
    try:
        return float(
            subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", wav_in],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except Exception:
        return 0.0


def build_intro(
    video_in: str,
    wav_in: str,
    out_path: str,
    hook_text: str = "",
    hook_position: str = "top",
    font_scale: float = 1.0,
    style: str = "classic",
    duration: float = None,
) -> str:
    """Build an 'intro' segment: the clip frozen on its first frame for
    `duration` seconds, with the viral hook burned on top and the voice-over
    audio playing. This is prepended to the original clip so the hook+VO play
    first, then the real clip begins.

    If hook_text is empty, the frozen frame still shows (with VO audio only).
    """
    from . import hooks as _hooks

    intro_duration = float(duration or 0.0)
    if intro_duration <= 0:
        # fall back to VO length
        intro_duration = wav_duration(wav_in)

    # 1) Freeze the first frame for intro_duration seconds, silent.
    frozen = out_path + ".frozen.mp4"
    run_command([
        "ffmpeg", "-y", "-i", video_in,
        "-frames:v", "1", "-f", "image2", out_path + ".first.png",
    ])
    run_command([
        "ffmpeg", "-y", "-loop", "1", "-i", out_path + ".first.png",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(intro_duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-shortest", frozen,
    ])

    step = frozen
    # 2) Burn the hook onto the frozen intro (if any).
    if hook_text.strip():
        hook_out = out_path + ".hook.mp4"
        _hooks.add_hook_to_video(
            frozen, hook_text, hook_out,
            position=hook_position, font_scale=font_scale,
            duration=intro_duration, style=style,
        )
        step = hook_out

    # 3) Mix the voice-over audio onto the intro. The VO is padded/looped to
    #    exactly intro_duration so the intro keeps its full length (no -shortest
    #    truncation to the raw VO length).
    final = out_path
    run_command([
        "ffmpeg", "-y", "-i", step, "-i", wav_in,
        "-filter_complex",
        f"[1:a]aloop=loop=-1:size=2000000000,apad=whole_dur={intro_duration:.3f},atrim=0:{intro_duration:.3f}[a]",
        "-map", "0:v:0", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac",
        final,
    ])

    # cleanup
    for f in (out_path + ".first.png", frozen, out_path + ".hook.mp4"):
        if os.path.isfile(f):
            os.remove(f)
    return final


def _get_duration(path: str) -> float:
    """Return media duration in seconds."""
    import subprocess
    try:
        out = subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', path],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return float(out)
    except Exception:
        return 0.0


def _has_audio_stream(path: str) -> bool:
    """Return True if the file has at least one audio stream."""
    import subprocess
    try:
        out = subprocess.check_output(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', path],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return 'audio' in out
    except Exception:
        return False


def concat_videos(video_a: str, video_b: str, out_path: str) -> str:
    """Concatenate two videos (concat filter, single-pass re-encode).

    Uses the concat *filter* (not demuxer) so stream parameters are normalised
    transparently.  Silent audio is injected for any input that lacks a real
    audio track.
    """
    has_a = _has_audio_stream(video_a)
    has_b = _has_audio_stream(video_b)

    if has_a and has_b:
        cmd = [
            "ffmpeg", "-y", "-i", video_a, "-i", video_b,
            "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", out_path,
        ]
    elif has_a and not has_b:
        dur_b = _get_duration(video_b)
        cmd = [
            "ffmpeg", "-y", "-i", video_a, "-i", video_b,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={dur_b:.3f}",
            "-filter_complex", "[0:v][0:a][1:v][2:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", out_path,
        ]
    elif not has_a and has_b:
        dur_a = _get_duration(video_a)
        cmd = [
            "ffmpeg", "-y", "-i", video_a, "-i", video_b,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={dur_a:.3f}",
            "-filter_complex", "[0:v][2:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", out_path,
        ]
    else:
        dur_a = _get_duration(video_a)
        dur_b = _get_duration(video_b)
        cmd = [
            "ffmpeg", "-y", "-i", video_a, "-i", video_b,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={dur_a:.3f}",
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={dur_b:.3f}",
            "-filter_complex", "[0:v][2:a][1:v][3:a]concat=n=2:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-pix_fmt", "yuv420p", out_path,
        ]

    run_command(cmd)
    return out_path


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
