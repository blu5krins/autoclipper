"""Viral hook text overlay (ported from OpenShorts hooks.py).

Renders a punchy hook phrase onto a rounded white box with a soft shadow and
burns it onto the clip via FFmpeg. The hook appears at the start of the clip
with an entrance animation and disappears after `hold_seconds` (matching the
OpenShorts behavior). Uses the Noto Serif Bold font (downloaded once into the
image) so the output matches OpenShorts exactly.
"""
import os
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSerif/NotoSerif-Bold.ttf"
FONT_DIR = "/usr/share/fonts/truetype/noto"
FONT_PATH = os.path.join(FONT_DIR, "NotoSerif-Bold.ttf")


def _ensure_font():
    """Download Noto Serif Bold once if missing (matches OpenShorts)."""
    if os.path.exists(FONT_PATH):
        return
    os.makedirs(FONT_DIR, exist_ok=True)
    try:
        req = urllib.request.Request(FONT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(FONT_PATH, "wb") as out:
            out.write(resp.read())
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Could not download Noto Serif font: {e}")


def _resolve_font_path():
    _ensure_font()
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    # Fallback to any locally available serif bold.
    for p in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if os.path.exists(p):
            return p
    return None


def create_hook_image(text, target_width, output_image_path="hook_overlay.png", font_scale=1.0):
    """Generate a white rounded box with black serif text (pixel-based wrap)."""
    padding_x = 30
    padding_y = 25
    line_spacing = 20
    cornerradius = 20
    shadow_offset = (5, 5)

    base_font_size = int(target_width * 0.05)
    font_size = int(base_font_size * font_scale)

    font_path = _resolve_font_path()
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception as e:
        print(f"⚠️ Warning: could not load font {font_path}, using default: {e}")
        font = ImageFont.load_default()

    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    max_text_width = target_width - (2 * padding_x)

    lines = []
    for p in text.split("\n"):
        if not p.strip():
            lines.append("")
            continue
        current_line = []
        for word in p.split():
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_text_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))

    max_line_width = 0
    text_heights = []
    for line in lines:
        if not line:
            text_heights.append(font_size)
            continue
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        max_line_width = max(max_line_width, w)
        text_heights.append(h)

    if not text_heights:
        total_text_height = font_size
    else:
        total_text_height = sum(text_heights) + (len(text_heights) - 1) * line_spacing

    box_width = max(max_line_width + (2 * padding_x), int(target_width * 0.3))
    box_height = total_text_height + (2 * padding_y)

    canvas_w = box_width + 40
    canvas_h = box_height + 40
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    shadow_box = [
        (20 + shadow_offset[0], 20 + shadow_offset[1]),
        (20 + box_width + shadow_offset[0], 20 + box_height + shadow_offset[1]),
    ]
    draw.rounded_rectangle(shadow_box, radius=cornerradius, fill=(0, 0, 0, 100))
    img = img.filter(ImageFilter.GaussianBlur(5))

    draw_final = ImageDraw.Draw(img)
    main_box = [(20, 20), (20 + box_width, 20 + box_height)]
    draw_final.rounded_rectangle(main_box, radius=cornerradius, fill=(255, 255, 255, 240))

    current_y = 20 + padding_y - 2
    for i, line in enumerate(lines):
        if not line:
            current_y += font_size + line_spacing
            continue
        bbox = draw_final.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_h = text_heights[i] if i < len(text_heights) else bbox[3] - bbox[1]
        x = 20 + (box_width - line_w) // 2
        draw_final.text((x, current_y), line, font=font, fill="black")
        current_y += line_h + line_spacing

    img.save(output_image_path)
    return output_image_path, canvas_w, canvas_h


def add_hook_to_video(video_path, text, output_path, position="top", font_scale=1.0,
                      size="M", entrance="fade", hold_seconds=5):
    """Overlay a hook text box onto a clip, OpenShorts-style.

    The hook appears at the start with an entrance animation and disappears
    after `hold_seconds` (fade out). position: top|center|bottom.
    size: S|M|L (maps to font_scale 0.7|1.0|1.4). entrance: fade|none.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video {video_path} not found")

    # Map size -> font scale (so the burned result matches the preview).
    size_scale = {"S": 0.7, "L": 1.4}.get((size or "M").upper(), 1.0)
    font_scale = font_scale * size_scale

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=s=x:p=0", video_path,
        ]
        res = subprocess.check_output(cmd).decode().strip().split("\n")[0]
        dims = res.split("x")
        video_width = int(dims[0])
        video_height = int(dims[1])
    except Exception as e:
        print(f"⚠️ FFprobe failed: {e}. Assuming 1080x1920")
        video_width, video_height = 1080, 1920

    target_box_width = int(video_width * 0.9)
    hook_filename = f"temp_hook_{os.path.basename(video_path)}.png"

    try:
        img_path, box_w, box_h = create_hook_image(
            text, target_box_width, hook_filename, font_scale=font_scale
        )
        overlay_x = (video_width - box_w) // 2
        if position == "center":
            overlay_y = (video_height - box_h) // 2
        elif position == "bottom":
            overlay_y = int(video_height * 0.70)
        else:
            overlay_y = int(video_height * 0.20)

        # Entrance + timed disappearance (OpenShorts style).
        # Ensure an alpha channel so fade can operate on it.
        fade_in = ",fade=t=in:st=0:d=0.3:alpha=1" if entrance != "none" else ""
        hold = max(1.0, float(hold_seconds))
        fade_out = f",fade=t=out:st={max(0.0, hold - 0.3):.2f}:d=0.3:alpha=1"
        ov_filter = f"[1:v]format=rgba{fade_in}{fade_out}[ov]"
        overlay_filter = f"[0:v][ov]overlay={overlay_x}:{overlay_y}:enable='lte(t,{hold:.2f})'"

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", img_path,
            "-filter_complex", f"{ov_filter};{overlay_filter}",
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-x264-params", "ref=4:me=hex:subme=7:trellis=1",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Error: {e.stderr.decode() if e.stderr else 'Unknown'}")
        raise e
    except Exception as e:
        print(f"❌ Hook Gen Error: {e}")
        raise e
    finally:
        if os.path.exists(hook_filename):
            os.remove(hook_filename)
