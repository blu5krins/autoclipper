"""Vertical 9:16 reframing with face/subject tracking.

Two modes, decided per scene:
  * TRACK   — single speaker: detect faces (MediaPipe, YOLO fallback) and pan a
              stabilized crop to keep them framed.
  * GENERAL — groups / wide shots: fit the full width over a blurred background.

MediaPipe is required. YOLO (ultralytics) is an optional soft-dependency used
only as a fallback when no face is found.
"""
import os
import subprocess
import sys
import urllib.request

import cv2
import numpy as np

from .utils import logger

VERTICAL_ASPECT = 9 / 16  # width / height

# MediaPipe FaceDetector (Tasks API) model, downloaded once and cached.
_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
_FACE_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "models", "blaze_face_short_range.tflite"
)

# --- Lazy singletons -------------------------------------------------------
_face_detector = None
_yolo_model = None
_yolo_unavailable = False


def _ensure_face_model():
    if not os.path.exists(_FACE_MODEL_PATH):
        os.makedirs(os.path.dirname(_FACE_MODEL_PATH), exist_ok=True)
        logger.info("Downloading face detection model...")
        urllib.request.urlretrieve(_FACE_MODEL_URL, _FACE_MODEL_PATH)
    return _FACE_MODEL_PATH


def _get_face_detector():
    global _face_detector
    if _face_detector is None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        _ensure_face_model()
        base_opts = BaseOptions(model_asset_path=_FACE_MODEL_PATH)
        opts = vision.FaceDetectorOptions(base_options=base_opts)
        _face_detector = vision.FaceDetector.create_from_options(opts)
    return _face_detector


def _get_mp_image(rgb):
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def _get_yolo():
    """Return a YOLO model, or None if ultralytics isn't installed."""
    global _yolo_model, _yolo_unavailable
    if _yolo_unavailable:
        return None
    if _yolo_model is None:
        try:
            from ultralytics import YOLO

            _yolo_model = YOLO("yolov8n.pt")
        except Exception as e:  # noqa: BLE001
            logger.info("YOLO fallback unavailable (%s); using faces only.", e)
            _yolo_unavailable = True
            return None
    return _yolo_model


# --- Camera + speaker tracking --------------------------------------------
class SmoothedCameraman:
    """'Heavy tripod' crop: stays put until the subject leaves a safe zone,
    then pans slowly toward them."""

    def __init__(self, video_width, video_height):
        self.video_width = video_width
        self.video_height = video_height
        self.current_center_x = video_width / 2
        self.target_center_x = video_width / 2

        self.crop_height = video_height
        self.crop_width = int(self.crop_height * VERTICAL_ASPECT)
        if self.crop_width > video_width:
            self.crop_width = video_width
            self.crop_height = int(self.crop_width / VERTICAL_ASPECT)

        self.safe_zone_radius = self.crop_width * 0.25

    def update_target(self, face_box):
        if face_box:
            x, _, w, _ = face_box
            self.target_center_x = x + w / 2

    def get_crop_box(self, force_snap=False):
        if force_snap:
            self.current_center_x = self.target_center_x
        else:
            diff = self.target_center_x - self.current_center_x
            if abs(diff) > self.safe_zone_radius:
                direction = 1 if diff > 0 else -1
                speed = 15.0 if abs(diff) > self.crop_width * 0.5 else 3.0
                self.current_center_x += direction * speed
                new_diff = self.target_center_x - self.current_center_x
                if (direction == 1 and new_diff < 0) or (direction == -1 and new_diff > 0):
                    self.current_center_x = self.target_center_x

        half_crop = self.crop_width / 2
        if self.current_center_x - half_crop < 0:
            self.current_center_x = half_crop
        if self.current_center_x + half_crop > self.video_width:
            self.current_center_x = self.video_width - half_crop

        x1 = max(0, int(self.current_center_x - half_crop))
        x2 = min(self.video_width, int(self.current_center_x + half_crop))
        return x1, 0, x2, self.video_height


class SpeakerTracker:
    """Picks the active speaker across frames with hysteresis to avoid jitter."""

    def __init__(self, cooldown_frames=30):
        self.active_speaker_id = None
        self.speaker_scores = {}
        self.switch_cooldown = cooldown_frames
        self.last_switch_frame = -1000
        self.next_id = 0
        self.known_faces = []

    def get_target(self, face_candidates, frame_number, width):
        current = []
        for face in face_candidates:
            x, _, w, _ = face["box"]
            center_x = x + w / 2

            best_id, min_dist = -1, width * 0.15
            for kf in self.known_faces:
                if frame_number - kf["last_frame"] > 30:
                    continue
                dist = abs(center_x - kf["center"])
                if dist < min_dist:
                    min_dist, best_id = dist, kf["id"]

            if best_id == -1:
                best_id = self.next_id
                self.next_id += 1

            self.known_faces = [kf for kf in self.known_faces if kf["id"] != best_id]
            self.known_faces.append(
                {"id": best_id, "center": center_x, "last_frame": frame_number}
            )
            current.append({"id": best_id, "box": face["box"], "score": face["score"]})

        for pid in list(self.speaker_scores.keys()):
            self.speaker_scores[pid] *= 0.85
            if self.speaker_scores[pid] < 0.1:
                del self.speaker_scores[pid]

        for cand in current:
            raw = cand["score"] / (width * width * 0.05)
            self.speaker_scores[cand["id"]] = self.speaker_scores.get(cand["id"], 0) + raw

        if not current:
            return None

        best, max_score = None, -1
        for cand in current:
            score = self.speaker_scores.get(cand["id"], 0)
            if cand["id"] == self.active_speaker_id:
                score *= 3.0
            if score > max_score:
                max_score, best = score, cand

        if not best:
            return None

        if best["id"] == self.active_speaker_id:
            return best["box"]

        if frame_number - self.last_switch_frame < self.switch_cooldown:
            old = next((c for c in current if c["id"] == self.active_speaker_id), None)
            if old:
                return old["box"]

        self.active_speaker_id = best["id"]
        self.last_switch_frame = frame_number
        return best["box"]


# --- Detection helpers -----------------------------------------------------
def detect_faces(frame):
    height, width = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = _get_mp_image(rgb)
    result = _get_face_detector().detect(mp_image)
    if not result.detections:
        return []
    candidates = []
    for det in result.detections:
        b = det.bounding_box
        x, y, w, h = int(b.origin_x), int(b.origin_y), int(b.width), int(b.height)
        candidates.append({"box": [x, y, w, h], "score": w * h})
    return candidates


def detect_person_yolo(frame):
    model = _get_yolo()
    if model is None:
        return None
    results = model(frame, verbose=False, classes=[0])
    best_box, max_area = None, 0
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = [int(i) for i in box.xyxy[0]]
            w, h = x2 - x1, y2 - y1
            if w * h > max_area:
                max_area = w * h
                best_box = [x1, y1, w, int(h * 0.4)]
    return best_box


def create_general_frame(frame, out_w, out_h):
    orig_h, orig_w = frame.shape[:2]

    bg_scale = out_h / orig_h
    bg_w = int(orig_w * bg_scale)
    bg = cv2.resize(frame, (bg_w, out_h))
    start_x = max(0, (bg_w - out_w) // 2)
    bg = bg[:, start_x : start_x + out_w]
    if bg.shape[1] != out_w:
        bg = cv2.resize(bg, (out_w, out_h))
    bg = cv2.GaussianBlur(bg, (51, 51), 0)

    scale = out_w / orig_w
    fg_h = int(orig_h * scale)
    fg = cv2.resize(frame, (out_w, fg_h))

    y_off = max(0, (out_h - fg_h) // 2)
    out = bg.copy()
    end = min(out_h, y_off + fg_h)
    out[y_off:end, :] = fg[: end - y_off, :]
    return out


# --- Scene strategy --------------------------------------------------------
def _detect_scenes(video_path):
    """Return list of (start_frame, end_frame) and fps. Falls back to one scene."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    try:
        from scenedetect import ContentDetector, SceneManager, open_video

        video = open_video(video_path)
        sm = SceneManager()
        sm.add_detector(ContentDetector())
        sm.detect_scenes(video=video)
        scenes = sm.get_scene_list()
        if scenes:
            return [(s.get_frames(), e.get_frames()) for s, e in scenes], video.frame_rate
    except Exception as e:  # noqa: BLE001
        logger.debug("Scene detection unavailable (%s); using single scene.", e)

    return [(0, total)], fps


def _analyze_strategies(video_path, scenes):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return ["TRACK"] * len(scenes)

    strategies = []
    for start_f, end_f in scenes:
        samples = [start_f + 5, (start_f + end_f) // 2, max(start_f, end_f - 5)]
        counts = []
        for f_idx in samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, f_idx))
            ret, frame = cap.read()
            if ret:
                counts.append(len(detect_faces(frame)))
        avg = sum(counts) / len(counts) if counts else 0
        strategies.append("GENERAL" if (avg > 1.2 or avg < 0.5) else "TRACK")
    cap.release()
    return strategies


# --- Main entry ------------------------------------------------------------
def reframe_clip(input_video: str, output_video: str, use_yolo: bool = True) -> bool:
    """Convert a horizontal clip into vertical 9:16 with subject tracking."""
    base = os.path.splitext(output_video)[0]
    temp_video = f"{base}_tmp_video.mp4"
    temp_audio = f"{base}_tmp_audio.aac"
    for p in (temp_video, temp_audio, output_video):
        if os.path.exists(p):
            os.remove(p)

    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        logger.error("Could not open clip for reframing: %s", input_video)
        return False
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    scenes, fps = _detect_scenes(input_video)
    strategies = _analyze_strategies(input_video, scenes)

    # For horizontal→vertical: use source WIDTH as output HEIGHT (taller output).
    # For already-vertical: keep source height as-is.
    is_landscape = src_w > src_h
    if is_landscape:
        out_h = src_w   # e.g. 1920 from a 1920x1080 source
    else:
        out_h = src_h   # already vertical, keep height
    out_w = int(out_h * VERTICAL_ASPECT)
    if out_w % 2:
        out_w += 1

    cameraman = SmoothedCameraman(src_w, src_h)
    tracker = SpeakerTracker(cooldown_frames=30)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{out_w}x{out_h}", "-pix_fmt", "bgr24", "-r", str(fps),
        "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-x264-params", "ref=4:me=hex:subme=7:trellis=1",
        "-pix_fmt", "yuv420p", "-an", temp_video,
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    cap = cv2.VideoCapture(input_video)
    frame_number = 0
    scene_idx = 0
    logger.info("Reframing %s (%d frames)...", os.path.basename(input_video), total)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if scene_idx < len(scenes):
            _, end_f = scenes[scene_idx]
            if frame_number >= end_f and scene_idx < len(scenes) - 1:
                scene_idx += 1

        strategy = strategies[scene_idx] if scene_idx < len(strategies) else "TRACK"

        if strategy == "GENERAL":
            out_frame = create_general_frame(frame, out_w, out_h)
            cameraman.current_center_x = src_w / 2
            cameraman.target_center_x = src_w / 2
        else:
            if frame_number % 2 == 0:
                candidates = detect_faces(frame)
                target = tracker.get_target(candidates, frame_number, src_w)
                if target:
                    cameraman.update_target(target)
                elif use_yolo:
                    person = detect_person_yolo(frame)
                    if person:
                        cameraman.update_target(person)

            is_scene_start = frame_number == scenes[scene_idx][0]
            x1, y1, x2, y2 = cameraman.get_crop_box(force_snap=is_scene_start)
            if x2 > x1 and y2 > y1:
                out_frame = cv2.resize(frame[y1:y2, x1:x2], (out_w, out_h))
            else:
                out_frame = cv2.resize(frame, (out_w, out_h))

        try:
            proc.stdin.write(out_frame.astype(np.uint8).tobytes())
        except BrokenPipeError:
            break
        frame_number += 1

    cap.release()
    proc.stdin.close()
    stderr = proc.stderr.read().decode(errors="ignore")
    proc.wait()

    if proc.returncode != 0:
        logger.error("FFmpeg reframe encode failed: %s", stderr[-500:])
        return False

    # Merge original audio back in.
    has_audio = (
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_video, "-vn", "-acodec", "copy", temp_audio],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
        == 0
        and os.path.exists(temp_audio)
    )

    if has_audio:
        merge = ["ffmpeg", "-y", "-i", temp_video, "-i", temp_audio,
                 "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", output_video]
    else:
        merge = ["ffmpeg", "-y", "-i", temp_video, "-c:v", "copy",
                 "-movflags", "+faststart", output_video]

    result = subprocess.run(merge, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for p in (temp_video, temp_audio):
        if os.path.exists(p):
            os.remove(p)

    if result.returncode != 0:
        logger.error("FFmpeg reframe merge failed: %s", result.stderr.decode(errors="ignore")[-500:])
        return False

    logger.info("Vertical clip saved: %s", output_video)
    return True
