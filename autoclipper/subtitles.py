"""Burned-in subtitles generated from word-level timestamps.

Builds an SRT from the words that fall inside each clip, then burns it into the
final clip with ffmpeg's subtitles filter (libass). Word-by-word timing gives
the classic short-form caption look.
"""
import os
import subprocess

from . import config
from .utils import logger, run_command


def _words_in_range(words, start, end):
    for w in words or []:
        ws, we = w.get("start"), w.get("end")
        if ws is None or we is None:
            continue
        if ws >= start and we <= end + 0.5:
            yield w


def build_srt(words, start, end, words_per_cue=None):
    """Return an SRT string for words within [start, end], times relative to start."""
    words_per_cue = words_per_cue or config.SUBTITLE_WORDS_PER_CUE
    selected = [
        {"word": w.get("word", "").strip(), "start": w["start"], "end": w["end"]}
        for w in _words_in_range(words, start, end)
        if w.get("word", "").strip()
    ]
    if not selected:
        return ""

    cues = []
    for i in range(0, len(selected), max(1, words_per_cue)):
        group = selected[i : i + words_per_cue]
        text = " ".join(g["word"] for g in group)
        cue_start = group[0]["start"] - start
        cue_end = group[-1]["end"] - start
        cues.append((cue_start, cue_end, text))

    def _fmt(t):
        ms = int(round((t - int(t)) * 1000))
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for idx, (cs, ce, text) in enumerate(cues, start=1):
        lines.append(f"{idx}\n{_fmt(cs)} --> {_fmt(ce)}\n{text}\n")
    return "\n".join(lines)


def _escape_filter_path(path: str) -> str:
    """Return a filtergraph-safe reference to a subtitle file.

    We run ffmpeg from the file's own directory and use a relative basename,
    which sidesteps Windows drive-letter escaping. Spaces/special chars are
    wrapped in single quotes.
    """
    name = os.path.basename(path)
    if any(ch in name for ch in " ':,[]=;"):
        return "'" + name + "'"
    return name


def burn_subtitles(video_path: str, srt_path: str, out_path: str) -> str:
    """Burn an SRT into a video, returning the output path on success.

    Uses the OpenShorts TikTok style: Arial Black, thick 4px black outline,
    no shadow, bottom-center alignment."""
    style = (
        f"FontName={_map_font(config.SUBTITLE_FONT)},"
        f"FontSize={config.SUBTITLE_FONT_SIZE},"
        f"PrimaryColour={config.SUBTITLE_PRIMARY},"
        f"OutlineColour={config.SUBTITLE_OUTLINE},"
        f"BackColour={config.SUBTITLE_BACKGROUND},"
        f"Bold=1,Outline=4,Shadow=0,Alignment=2,"
        f"MarginV={config.SUBTITLE_MARGIN_V}"
    )
    vf = f"subtitles={_escape_filter_path(srt_path)}:force_style='{style}'"
    cwd = os.path.dirname(os.path.abspath(video_path))
    run_command(
        [
            "ffmpeg", "-y", "-i", os.path.basename(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-x264-params", "ref=4:me=hex:subme=7:trellis=1", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
            os.path.basename(out_path),
        ],
        cwd=cwd,
    )
    return out_path


def add_subtitles(clips, transcript, output_dir, burn=True):
    """For each clip, generate and (optionally) burn subtitles.

    Updates each clip dict with 'srt' (path) and, when burned, replaces 'file'
    with the subtitled version and records 'subtitled_file'.
    """
    words = transcript.get("words", [])
    for clip in clips:
        cs, ce = clip.get("start"), clip.get("end")
        if cs is None or ce is None:
            continue
        srt = build_srt(words, cs, ce)
        if not srt:
            logger.warning("No words for clip %s; skipping subtitles.", clip.get("index"))
            continue

        srt_name = clip["file"].rsplit(".", 1)[0] + ".srt"
        srt_path = os.path.join(output_dir, srt_name)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt)
        clip["srt"] = srt_name

        if not burn:
            continue

        src = os.path.join(output_dir, clip["file"])
        if not os.path.exists(src):
            continue
        sub_name = clip["file"].rsplit(".", 1)[0] + "_sub.mp4"
        sub_path = os.path.join(output_dir, sub_name)
        try:
            burn_subtitles(src, srt_path, sub_path)
            clip["subtitled_file"] = sub_name
            if os.path.exists(sub_path):
                os.remove(src)
                clip["file"] = sub_name
        except RuntimeError as e:
            logger.error("Failed to burn subtitles for clip %s: %s", clip.get("index"), e)
    return clips


# --- Editable / styled subtitle re-burn (dashboard "Auto Subtitle") ---------
def hex_to_ass(hex_color: str) -> str:
    """Convert '#RRGGBB' to ASS colour '&H00BBGGRR&' (alpha 00 = opaque)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H00{b}{g}{r}&"
    return "&H00FFFFFF&"


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h = cs // 360000
    m = (cs % 360000) // 6000
    s = (cs % 6000) // 100
    cc = cs % 100
    return f"{h:02d}:{m:02d}:{s:02d}.{cc:02d}"


def _map_font(name: str) -> str:
    """Map a font name to one actually available in the container so the
    burned result matches what the browser preview shows."""
    n = (name or "").strip().lower()
    aliases = {
        "arial": "Liberation Sans",
        "arial black": "Liberation Sans:bold",
        "helvetica": "Liberation Sans",
        "liberation sans": "Liberation Sans",
        "times new roman": "Liberation Serif",
        "times": "Liberation Serif",
        "courier new": "Liberation Mono",
        "verdana": "DejaVu Sans",
        "georgia": "DejaVu Serif",
        "impact": "Liberation Sans",
    }
    return aliases.get(n, name or config.SUBTITLE_FONT)


def build_ass(cues: list, style: dict) -> str:
    """Build an ASS subtitle string from edited cues + styling options.

    `cues` is a list of {"start", "end", "text"} (seconds, relative to clip).
    `style` keys: font, font_size, text_color, outline_color, box_color,
    box_opacity (0-100), highlight_color, highlight (bool), box (bool), margin_v,
    position ("top" | "middle" | "bottom").
    When highlight is on, each cue uses karaoke timing so the spoken word fills
    with `highlight_color` (the classic short-form caption effect).
    """
    font = _map_font(style.get("font", config.SUBTITLE_FONT))
    size = int(style.get("font_size", config.SUBTITLE_FONT_SIZE))
    primary = hex_to_ass(style.get("text_color", "#FFFFFF"))
    outline = hex_to_ass(style.get("outline_color", "#000000"))
    highlight = hex_to_ass(style.get("highlight_color", "#FFFF00"))
    margin_v = int(style.get("margin_v", config.SUBTITLE_MARGIN_V))
    position = (style.get("position", "bottom") or "bottom").lower()
    use_box = bool(style.get("box", False))
    use_highlight = bool(style.get("highlight", False))

    box_opacity = int(style.get("box_opacity", 50))
    alpha = max(0, min(255, int(round(box_opacity / 100 * 255))))
    box_color = hex_to_ass(style.get("box_color", "#000000"))
    back = f"&H{alpha:02X}{box_color[2:8]}"  # &H<AABBGGRR>

    # Match OpenShorts TikTok style: BorderStyle 1, thick 4px outline, no shadow.
    border_style = 3 if use_box else 1  # 3 = opaque box behind text
    outline_width = 4 if not use_box else 1
    shadow = 0
    # Alignment: 1=top-left, 2=bottom-center, 5=middle-center, etc. We use the
    # center variants: top=6, middle=10, bottom=2 (horizontal center).
    alignment = {"top": 6, "middle": 10, "bottom": 2}.get(position, 2)
    # Karaoke reveals SecondaryColour over PrimaryColour as each word plays.
    secondary = highlight if use_highlight else primary

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV",
        f"Style: Default,{font},{size},{primary},{secondary},{outline},{back},"
        f"-1,0,0,0,100,100,0,0,{border_style},{outline_width},{shadow},{alignment},10,10,{margin_v}",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]

    events = []
    for cue in cues or []:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        start = float(cue.get("start", 0.0))
        end = float(cue.get("end", start + 1.0))
        words = text.split()
        n = len(words)
        if use_highlight and n > 0:
            dur = max(1, int(round((end - start) * 100 / n)))
            line = "".join(f"{{\\k{dur}}}{w} " for w in words).strip()
        else:
            line = text
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{line}"
        )

    return "\n".join(header + events) + "\n"


def burn_ass(video_path: str, ass_path: str, out_path: str) -> str:
    """Burn an ASS subtitle file into a video, returning the output path."""
    cwd = os.path.dirname(os.path.abspath(video_path))
    vf = f"subtitles={_escape_filter_path(ass_path)}"
    run_command(
        [
            "ffmpeg", "-y", "-i", os.path.basename(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-x264-params", "ref=4:me=hex:subme=7:trellis=1", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart",
            os.path.basename(out_path),
        ],
        cwd=cwd,
    )
    return out_path
