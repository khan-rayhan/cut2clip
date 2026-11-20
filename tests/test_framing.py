"""Tests for auto-framing: pure helpers plus real video runs."""

import subprocess

import pytest

from src.framing import (Framer, crop_x_for_center, decide_layout,
                         detect_faces_mediapipe, ema_smooth)


def test_ema_smooth():
    values = [0.0, 10.0, 10.0, 10.0]
    out = ema_smooth(values, alpha=0.3)
    assert out[0] == 0.0
    # Smoothing pulls the jump up gradually, never all at once.
    assert out[1] == pytest.approx(3.0)
    assert out[2] == pytest.approx(5.1)
    assert out[3] == pytest.approx(6.57)
    assert all(b - a < 10.0 for a, b in zip(out, out[1:]))


def test_crop_x_for_center():
    assert crop_x_for_center(1280, 405, 100) == 0  # clamped left
    assert crop_x_for_center(1280, 405, 640) == 438  # centred (640 - 405/2 = 437.5, rounds to 438)
    assert crop_x_for_center(1280, 405, 1200) == 875  # clamped right


def test_decide_layout():
    assert decide_layout([1, 1, 1, 1, 1, 1, 1, 1]) == "single"
    assert decide_layout([2, 2, 2, 2, 2, 2, 1, 1]) == "split"
    assert decide_layout([2, 2, 1, 1, 1, 1, 1, 1]) == "single"  # too brief


def _make_subject_video(path, duration=10):
    """1280x720 video with a white rectangle sliding left to right,
    plus a tone track."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i",
         f"color=c=black:size=1280x720:rate=30:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-vf", "drawbox=x='100+80*t':y=260:w=120:h=200:color=white:t=fill",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", path],
        check=True)


def _dims(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path], text=True)
    lines = [line.split(",") for line in out.strip().splitlines()]
    return [(int(w), int(h)) for w, h in lines]


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def test_reframe_synthetic_video(tmp_path):
    src = tmp_path / "src.mp4"
    _make_subject_video(str(src))
    framer = Framer(str(src))
    layout = framer.compute_trajectory()
    assert layout == "single"  # no real face in a drawn rectangle
    out = tmp_path / "vertical.mp4"
    framer.reframe_video(str(out))
    assert (1080, 1920) in _dims(str(out))
    assert abs(_duration(str(out)) - 10.0) < 0.6


def test_mediapipe_finds_real_face(tmp_path):
    """Rick Astley sings facing the camera; MediaPipe should find
    his face in at least some samples."""
    src = tmp_path / "rick.mp4"
    yt_dlp = str(__import__("pathlib").Path(__file__).parent.parent
                 / ".venv" / "bin" / "yt-dlp")
    dl = subprocess.run(
        [yt_dlp, "-q", "--no-check-certificate",
         "-f", "bv*[height<=720]",
         "--download-sections", "*00:00:30-00:00:45",
         "-o", str(src),
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        capture_output=True, text=True)
    if dl.returncode != 0 or not src.exists():
        pytest.skip("Could not download the test clip (network).")
    import cv2
    cap = cv2.VideoCapture(str(src))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    found = 0
    checked = 0
    # Sample ten frames spread across the whole clip: the face is
    # not in every shot, so the first five seconds alone are not a
    # fair check.
    for i in range(10):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i * total / 10))
        ok, frame = cap.read()
        if not ok:
            break
        checked += 1
        if detect_faces_mediapipe(frame):
            found += 1
    cap.release()
    assert found >= 3, f"MediaPipe found a face in only {found}/{checked} samples"
    framer = Framer(str(src))
    framer.compute_trajectory()
    out = tmp_path / "vertical.mp4"
    framer.reframe_video(str(out))
    assert (1080, 1920) in _dims(str(out))
    assert abs(_duration(str(out)) - 15.0) < 1.0
