"""Gaming layout builder for AutoClipper.

Takes a single gaming recording (webcam + gameplay already in one frame) and
lets the user define two rectangular regions — the webcam ("cam") and the
gameplay ("game"). It then composes them into a single vertical 9:16 video
with a configurable layout:

    - "cam_top"    : cam on top, gameplay below
    - "game_top"   : gameplay on top, cam below
    - "side"       : cam left, gameplay right (split vertically)

Boxes are normalized (0..1) relative to the source resolution so they survive
any resolution. Built with FFmpeg crop + scale + vstack/hstack.
"""
import subprocess

from .utils import logger


def _box_px(box, vw, vh):
    """Convert a normalized {x,y,w,h} box to integer pixel coords."""
    x = int(round(box.get("x", 0.0) * vw))
    y = int(round(box.get("y", 0.0) * vh))
    w = int(round(box.get("w", 0.1) * vw))
    h = int(round(box.get("h", 0.1) * vh))
    # Clamp to valid crop bounds (ffmpeg needs even dimensions).
    x = max(0, min(x, vw - 2))
    y = max(0, min(y, vh - 2))
    w = max(2, min(w, vw - x))
    h = max(2, min(h, vh - y))
    if w % 2:
        w -= 1
    if h % 2:
        h -= 1
    return x, y, w, h


def _probe(video_path):
    import json
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,duration,codec_type",
        "-of", "json", video_path,
    ]
    out = subprocess.check_output(cmd).decode()
    info = json.loads(out)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        # Fallback: first stream that has width/height.
        video = next((s for s in streams if "width" in s and "height" in s), None)
    if video is None:
        raise RuntimeError("No video stream found in source")
    return int(video["width"]), int(video["height"])


def build_gaming_video(source, cam_box, game_box, layout="cam_top",
                       out_path=None, target_w=720, target_h=1280,
                       max_duration=300):
    """Build a 9:16 gaming video from two regions of a single source.

    cam_box / game_box: normalized {x, y, w, h} in 0..1.
    layout: "cam_top" | "game_top" | "side".
    Returns out_path on success.
    """
    if not out_path:
        raise ValueError("out_path required")
    if not cam_box or not game_box:
        raise ValueError("Both cam_box and game_box are required")

    vw, vh = _probe(source)
    cx, cy, cw, ch = _box_px(cam_box, vw, vh)
    gx, gy, gw, gh = _box_px(game_box, vw, vh)

    layout = (layout or "cam_top").lower()
    # Downscale the source first so we never process 4K frames (huge speedup
    # for high-res gameplay recordings) while keeping aspect for crop math.
    pre_scale = "scale=1280:-2"
    if layout == "side":
        # Each region scaled to half width (target_w/2), stacked vertically.
        half_w = target_w // 2
        cam_scale = f"scale={half_w}:-2"
        game_scale = f"scale={half_w}:-2"
        # Stack horizontally (cam left, game right)
        filter_complex = (
            f"[0:v]{pre_scale},crop={cw}:{ch}:{cx}:{cy},{cam_scale}[cam];"
            f"[0:v]{pre_scale},crop={gw}:{gh}:{gx}:{gy},{game_scale}[game];"
            f"[cam][game]hstack=inputs=2[outv]"
        )
        # Result is half_w*2 x variable; force target size after.
        filter_complex += f";[outv]scale={target_w}:{target_h}[v]"
        out_label = "[v]"
    else:
        # Vertical stack. Each region scaled to full target width.
        cam_scale = f"scale={target_w}:-2"
        game_scale = f"scale={target_w}:-2"
        if layout == "game_top":
            top, top_scale = (gx, gy, gw, gh), game_scale
            bot, bot_scale = (cx, cy, cw, ch), cam_scale
        else:  # cam_top (default)
            top, top_scale = (cx, cy, cw, ch), cam_scale
            bot, bot_scale = (gx, gy, gw, gh), game_scale
        tx, ty, tw, th = top[:4]
        bx, by, bw, bh = bot[:4]
        filter_complex = (
            f"[0:v]{pre_scale},crop={tw}:{th}:{tx}:{ty},{top_scale}[t];"
            f"[0:v]{pre_scale},crop={bw}:{bh}:{bx}:{by},{bot_scale}[b];"
            f"[t][b]vstack=inputs=2[outv];"
            f"[outv]scale={target_w}:{target_h}[v]"
        )
        out_label = "[v]"

    cmd = [
        "ffmpeg", "-y", "-i", source,
        "-filter_complex", filter_complex,
        "-map", out_label,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-threads", "0",
        "-pix_fmt", "yuv420p",
        "-t", str(max_duration),
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]
    logger.info("Building gaming layout '%s' -> %s", layout, out_path)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg gaming layout failed: {e.stderr.decode()[:500]}")
    return out_path
