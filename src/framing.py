"""Auto-framing for Phase 3: turn a landscape clip into 1080x1920.

The subject (largest face, else largest detected person, else the
centre of the frame) is tracked with an exponential moving average
so the crop never jumps. One subject means a full 9:16 crop. Two or
more subjects held for at least 3 seconds means split-screen:
content on top, speaker on the bottom.

Detection is detector-agnostic: MediaPipe Face Detection is the
primary detector (CPU-friendly), YOLOv8 person detection is the
fallback and the GPU path. Both are imported lazily so a machine
without one of them still runs.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import cv2
import numpy as np

OUT_W, OUT_H = 1080, 1920
SPLIT_TOP_FRAC = 0.55  # top part of a split-screen frame

# ---------------------------------------------------------------- pure helpers

def ema_smooth(values: list[float], alpha: float = 0.3) -> list[float]:
    """Exponential moving average. The first value passes through."""
    out: list[float] = []
    current: float | None = None
    for value in values:
        current = value if current is None else alpha * value + (1 - alpha) * current
        out.append(current)
    return out


def crop_x_for_center(frame_w: int, crop_w: int, cx: float) -> int:
    """Left edge of a crop of width ``crop_w`` centred on ``cx``,
    clamped so the crop stays inside the frame."""
    x = int(round(cx - crop_w / 2))
    return max(0, min(frame_w - crop_w, x))


def decide_layout(n_faces_per_sample: list[int],
                  min_seconds: float = 3.0,
                  sample_fps: float = 2.0) -> str:
    """'split' when two or more faces are visible for at least
    ``min_seconds`` of sampled time, else 'single'."""
    need = int(min_seconds * sample_fps)
    return "split" if sum(1 for n in n_faces_per_sample if n >= 2) >= need else "single"


# ---------------------------------------------------------------- detectors

_mediapipe_detector = None
_MEDIAPIPE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")


def _mediapipe_model_path() -> str:
    """Local copy of the BlazeFace model, downloaded once on demand."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "models", "blaze_face_short_range.tflite")
    path = os.path.normpath(path)
    if not os.path.exists(path):
        import urllib.request
        os.makedirs(os.path.dirname(path), exist_ok=True)
        urllib.request.urlretrieve(_MEDIAPIPE_MODEL_URL, path)
    return path


def detect_faces_mediapipe(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Face boxes (x, y, w, h) in pixels, or [] when MediaPipe is
    missing or finds nothing. Uses the Tasks API (the legacy
    Solutions API was removed in mediapipe 1.x)."""
    global _mediapipe_detector
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceDetector, FaceDetectorOptions)
    except ImportError:
        return []
    if _mediapipe_detector is None:
        try:
            options = FaceDetectorOptions(
                base_options=BaseOptions(
                    model_asset_path=_mediapipe_model_path()),
                min_detection_confidence=0.5)
            _mediapipe_detector = FaceDetector.create_from_options(options)
        except Exception:
            return []
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = _mediapipe_detector.detect(image)
    boxes = []
    for det in result.detections:
        bb = det.bounding_box
        boxes.append((bb.origin_x, bb.origin_y, bb.width, bb.height))
    return boxes


_yolo_session = None
_yolo_failed = False


def _yolo_model_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "models", "yolov8n.onnx"))


def detect_persons_yolo(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Person boxes (x, y, w, h) via YOLOv8n on ONNX Runtime, or []
    when onnxruntime is missing or finds nobody. The model loads
    once and is reused. ONNX Runtime is used instead of ultralytics
    plus torch: it is a 12 MB model and a small runtime instead of a
    2 GB dependency, which matters for a desktop app download.
    YOLOv8 output is [1, 84, 8400]: 4 box values plus 80 class
    scores per anchor; class 0 is "person"."""
    global _yolo_session, _yolo_failed
    if _yolo_failed:
        return []
    try:
        import onnxruntime as ort
    except ImportError:
        _yolo_failed = True
        return []
    if _yolo_session is None:
        try:
            _yolo_session = ort.InferenceSession(
                _yolo_model_path(), providers=["CPUExecutionProvider"])
        except Exception:
            _yolo_failed = True
            return []
    h, w = frame.shape[:2]
    size = 640
    scale = min(size / w, size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(frame, (new_w, new_h))
    padded = np.full((size, size, 3), 114, dtype=np.uint8)
    padded[:new_h, :new_w] = resized
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None, ...]
    output = _yolo_session.run(None, {"images": tensor})[0][0]  # [84, 8400]
    output = output.T  # [8400, 84]
    scores = output[:, 4:]
    best_class = scores.argmax(axis=1)
    best_score = scores.max(axis=1)
    keep = (best_class == 0) & (best_score > 0.5)
    if not keep.any():
        return []
    boxes_xywh = output[keep, :4]
    boxes_xywh[:, 0] -= boxes_xywh[:, 2] / 2  # cx -> x1
    boxes_xywh[:, 1] -= boxes_xywh[:, 3] / 2  # cy -> y1
    # Undo the letterbox: back to original frame pixels.
    boxes_xywh /= scale
    boxes = boxes_xywh.tolist()
    confidences = best_score[keep].tolist()
    indices = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.45)
    result = []
    for i in indices:
        x, y, bw, bh = (int(v) for v in boxes[i])
        result.append((max(0, x), max(0, y),
                       min(bw, w - max(0, x)), min(bh, h - max(0, y))))
    return result


def pick_subject(frame: np.ndarray) -> tuple[int, int, int, int] | None:
    """The subject box to track: largest face, else largest person."""
    faces = detect_faces_mediapipe(frame)
    if faces:
        return max(faces, key=lambda b: b[2] * b[3])
    persons = detect_persons_yolo(frame)
    if persons:
        return max(persons, key=lambda b: b[2] * b[3])
    return None


# ---------------------------------------------------------------- framer

class Framer:
    """Computes a crop trajectory for one video, then reframes it."""

    def __init__(self, video_path: str, sample_fps: float = 2.0,
                 alpha: float = 0.3):
        self.video_path = video_path
        self.sample_fps = sample_fps
        self.alpha = alpha
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video {video_path!r}")
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        self.duration = self.frame_count / self.fps if self.fps else 0.0
        self.crop_w = int(round(self.h * 9 / 16))
        self.layout = "single"
        self.centers: list[float] = []  # smoothed subject centre-x per sample

    def compute_trajectory(self) -> str:
        """Sample frames, find the subject, smooth the centre-x.
        Returns the layout ('single' or 'split')."""
        cap = cv2.VideoCapture(self.video_path)
        step = max(1, int(round(self.fps / self.sample_fps)))
        raw_centers: list[float] = []
        face_counts: list[int] = []
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                faces = detect_faces_mediapipe(frame)
                box = None
                if faces:
                    box = max(faces, key=lambda b: b[2] * b[3])
                else:
                    persons = detect_persons_yolo(frame)
                    if persons:
                        box = max(persons, key=lambda b: b[2] * b[3])
                face_counts.append(len(faces))
                if box is not None:
                    raw_centers.append(box[0] + box[2] / 2)
                else:
                    raw_centers.append(self.w / 2)
            index += 1
        cap.release()
        self.centers = ema_smooth(raw_centers, self.alpha)
        self.layout = decide_layout(face_counts, sample_fps=self.sample_fps)
        return self.layout

    def _center_at(self, t: float) -> float:
        """Smoothed subject centre-x at time ``t`` (linear interp)."""
        if not self.centers:
            return self.w / 2
        pos = t * self.sample_fps
        i = int(pos)
        if i >= len(self.centers) - 1:
            return self.centers[-1]
        frac = pos - i
        return self.centers[i] * (1 - frac) + self.centers[i + 1] * frac

    def _reframe_frame(self, frame: np.ndarray, t: float) -> np.ndarray:
        cx = self._center_at(t)
        if self.layout == "single":
            x = crop_x_for_center(self.w, self.crop_w, cx)
            crop = frame[:, x:x + self.crop_w]
            return cv2.resize(crop, (OUT_W, OUT_H))
        # Split-screen: content on top, speaker on the bottom.
        top_h = int(OUT_H * SPLIT_TOP_FRAC)
        bottom_h = OUT_H - top_h
        content = cv2.resize(frame, (OUT_W, top_h))
        speaker_w = int(round(bottom_h * 1.25))
        x = crop_x_for_center(self.w, speaker_w, cx)
        speaker = cv2.resize(frame[:, x:x + speaker_w], (OUT_W, bottom_h))
        return np.vstack([content, speaker])

    def reframe_video(self, output_path: str) -> str:
        """Write the reframed video (video only) and mux the original
        audio back, producing an H.264/AAC MP4 at 1080x1920."""
        if not self.centers:
            self.compute_trajectory()
        tmp_video = os.path.join(tempfile.gettempdir(),
                                 "shorts-reframe-video.mp4")
        cap = cv2.VideoCapture(self.video_path)
        writer = cv2.VideoWriter(
            tmp_video, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (OUT_W, OUT_H))
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            out = self._reframe_frame(frame, index / self.fps)
            writer.write(out)
            index += 1
        cap.release()
        writer.release()
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-i", tmp_video, "-i", self.video_path,
               "-map", "0:v:0", "-map", "1:a:0?",
               "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", "-movflags", "+faststart",
               output_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            os.remove(tmp_video)
        except OSError:
            pass
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg reframe mux failed: {result.stderr[-300:]}")
        return output_path
