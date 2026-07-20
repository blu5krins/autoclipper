"""AutoClipper CLI.

Examples:
    python main.py -i "https://www.youtube.com/watch?v=..." -o output
    python main.py -i path/to/video.mp4 --model whisper-large-v3
"""
import argparse
import sys

from autoclipper.pipeline import run
from autoclipper.utils import logger, setup_logging


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Turn long videos into viral short clips (Groq Whisper + Gemini)."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="YouTube URL or path to a local video file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory (default: output).",
    )
    parser.add_argument(
        "--model",
        dest="whisper_model",
        default=None,
        help="Groq Whisper model (whisper-large-v3-turbo | whisper-large-v3).",
    )
    parser.add_argument(
        "--gemini-model",
        default=None,
        help="Gemini model for viral moment detection.",
    )
    parser.add_argument(
        "--groq-key", default=None, help="Groq API key (overrides GROQ_API_KEY)."
    )
    parser.add_argument(
        "--gemini-key",
        default=None,
        help="Gemini API key (overrides GEMINI_API_KEY).",
    )
    parser.add_argument(
        "--no-vertical",
        action="store_true",
        help="Skip vertical 9:16 reframing (keep original aspect ratio).",
    )
    parser.add_argument(
        "--no-yolo",
        action="store_true",
        help="Disable optional YOLO person fallback during reframing.",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip burning subtitles from word timestamps.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging(args.verbose)
    try:
        result = run(
            source=args.input,
            output_dir=args.output,
            groq_key=args.groq_key,
            gemini_key=args.gemini_key,
            whisper_model=args.whisper_model,
            gemini_model=args.gemini_model,
            vertical=not args.no_vertical,
            use_yolo=not args.no_yolo,
            subtitles=not args.no_subtitles,
        )
    except Exception as e:  # noqa: BLE001 - surface a clean CLI error
        logger.error("Pipeline failed: %s", e)
        return 1

    print(f"\n[OK] {len(result['clips'])} clip(s) generated in '{args.output}':")
    for clip in result["clips"]:
        print(
            f"  [{clip['index']}] {clip['start']:.1f}-{clip['end']:.1f}s  "
            f"{clip['title']}  ->  {clip['file']}"
        )

    if result.get("clips") and "vertical_file" in result["clips"][0]:
        print("\n[OK] All clips reframed to vertical 9:16.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
