"""AutoClipper — turn long videos into viral short clips.

Core pipeline: ingest -> transcribe (Groq Whisper) -> detect viral moments
(Gemini) -> cut clips (FFmpeg).
"""

__version__ = "0.1.0"
