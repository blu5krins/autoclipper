"""Gaming layout + Chat-split builder for AutoClipper.

Gaming layout takes a single gaming recording (webcam + gameplay already in one
frame) and lets the user define two rectangular regions — the webcam ("cam")
and the gameplay ("game"). It then composes them into a single vertical 9:16
video with a configurable layout:

    - "cam_top"    : cam on top, gameplay below
    - "game_top"   : gameplay on top, cam below
    - "side"       : cam left, gameplay right (split vertically)

Chat-split does the same for two-person interview/podcast clips: person 1
on top, person 2 on bottom. Boxes can be auto-detected via face detection.

Boxes are normalized (0..1) relative to the source resolution so they survive
any resolution. Built with FFmpeg crop + scale + vstack/hstack.
"""
import json
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


# --- Chat-split (two-person interview/podcast) --------------------------------

def detect_chat_regions(video_path: str, num_frames: int = 5):
    """Auto-detect two-person regions using MediaPipe face detection.

    Samples `num_frames` evenly across the clip, runs face detection,
    clusters face positions into two groups (left/right), and returns
    normalized bounding boxes for each person.
    
    Returns (person1_box, person2_box) or raises if <2 faces found.
    Each box: {"x", "y", "w", "h"} in normalized 0..1 coordinates.
    """
    try:
        import cv2
        from .reframe import detect_faces
    except ImportError:
        raise RuntimeError("OpenCV required for auto-detect chat regions")

    vw, vh = _probe(video_path)
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 1:
        cap.release()
        raise RuntimeError("Could not read video")

    sample_positions = [int(total * i / (num_frames + 1)) for i in range(1, num_frames + 1)]
    all_faces = []

    for pos in sample_positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret:
            continue
        faces = detect_faces(frame)
        for f in faces:
            bx, by, bw, bh = f["box"]
            cx = (bx + bw / 2) / vw   # normalized center x
            cy = (by + bh / 2) / vh   # normalized center y
            all_faces.append({"cx": cx, "cy": cy, "box": [bx, by, bw, bh]})
    cap.release()

    if len(all_faces) < 2:
        raise RuntimeError(
            f"Only {len(all_faces)} face(s) detected (need at least 2 for chat split)"
        )

    # Simple k-means clustering (k=2) on centers
    import random
    random.seed(42)
    c1 = random.choice(all_faces)
    c2 = random.choice([f for f in all_faces if f != c1])
    for _ in range(10):
        g1, g2 = [], []
        for f in all_faces:
            d1 = (f["cx"] - c1["cx"])**2 + (f["cy"] - c1["cy"])**2
            d2 = (f["cx"] - c2["cx"])**2 + (f["cy"] - c2["cy"])**2
            (g1 if d1 <= d2 else g2).append(f)
        if g1 and g2:
            c1 = {"cx": sum(f["cx"] for f in g1) / len(g1), "cy": sum(f["cy"] for f in g1) / len(g1)}
            c2 = {"cx": sum(f["cx"] for f in g2) / len(g2), "cy": sum(f["cy"] for f in g2) / len(g2)}

    # Build normalized boxes (face region * 3 for upper-body context)
    def make_box(cluster):
        if not cluster:
            return {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.5}
        boxes = [f["box"] for f in cluster]
        min_x = min(b[0] for b in boxes)
        min_y = min(b[1] for b in boxes)
        max_x = max(b[0] + b[2] for b in boxes)
        max_y = max(b[1] + b[3] for b in boxes)
        # Expand to upper-body
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        bw = (max_x - min_x) * 2.5
        bh = (max_y - min_y) * 4.0
        return {
            "x": max(0.0, (cx - bw / 2) / vw),
            "y": max(0.0, (cy - bh / 2) / vh),
            "w": min(1.0, bw / vw),
            "h": min(1.0, bh / vh),
        }

    # Order: person1 = top/left, person2 = bottom/right
    g1, g2 = [], []
    for f in all_faces:
        d1 = (f["cx"] - c1["cx"])**2 + (f["cy"] - c1["cy"])**2
        d2 = (f["cx"] - c2["cx"])**2 + (f["cy"] - c2["cy"])**2
        (g1 if d1 <= d2 else g2).append(f)

    p1 = make_box(g1)
    p2 = make_box(g2)

    # Sort by vertical position (top person first)
    if p1["y"] > p2["y"]:
        p1, p2 = p2, p1

    return p1, p2


def build_chat_split(source: str, person1_box: dict, person2_box: dict,
                     out_path: str, target_w: int = 720, target_h: int = 1280):
    """Build a 9:16 split-screen video with person 1 on top, person 2 below.

    person1_box / person2_box: normalized {x, y, w, h} in 0..1.
    Returns out_path on success.
    """
    vw, vh = _probe(source)
    p1x, p1y, p1w, p1h = _box_px(person1_box, vw, vh)
    p2x, p2y, p2w, p2h = _box_px(person2_box, vw, vh)

    pre_scale = "scale=1280:-2"
    top_scale = f"scale={target_w}:-2"
    bot_scale = f"scale={target_w}:-2"

    filter_complex = (
        f"[0:v]{pre_scale},crop={p1w}:{p1h}:{p1x}:{p1y},{top_scale}[t];"
        f"[0:v]{pre_scale},crop={p2w}:{p2h}:{p2x}:{p2y},{bot_scale}[b];"
        f"[t][b]vstack=inputs=2[outv];"
        f"[outv]scale={target_w}:{target_h}[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-i", source,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-threads", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        out_path,
    ]
    logger.info("Building chat-split -> %s", out_path)
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg chat-split failed: {e.stderr.decode()[:500]}")
    return out_path


def auto_chat_split_clip(source: str, out_path: str, target_w: int = 720, target_h: int = 1280):
    """Auto-detect two people and produce a 9:16 split-screen video in one step.

    Detects faces, clusters into two groups, crops each, stacks vertically.
    Falls back gracefully if <2 faces are found (raises RuntimeError).
    """
    p1, p2 = detect_chat_regions(source)
    return build_chat_split(source, p1, p2, out_path, target_w, target_h)
