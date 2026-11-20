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


# ---------------------------------------------------------------- split layout

def test_fit_size_and_panel_crop_keep_aspect():
    from src.framing import fit_size, panel_crop_size
    assert fit_size(1920, 1080, 1080, 1056) == (1080, 608)
    for fw, fh in ((1920, 1080), (1280, 720), (1080, 1080)):
        cw, ch = panel_crop_size(fw, fh, 1080, 864)
        assert cw <= fw and ch <= fh
        assert abs(cw / ch - 1080 / 864) < 0.01


def test_split_layout_does_not_distort(tmp_path):
    """A round object must stay round in both panels (it used to come
    out 1.74x too tall on top and 0.80x too squat at the bottom)."""
    import cv2
    import numpy as np

    from src import framing

    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "color=c=gray:size=1920x1080:rate=5:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    framer = Framer(str(src))
    framer.layout = "split"
    framer.centers = [960.0, 960.0]
    frame = np.full((1080, 1920, 3), 40, np.uint8)
    cv2.circle(frame, (960, 540), 200, (255, 255, 255), -1)
    out = framer._reframe_frame(frame, 0.0)
    assert out.shape == (1920, 1080, 3)

    top_h = int(1920 * framing.SPLIT_TOP_FRAC)
    for region in (out[:top_h], out[top_h:]):
        ys, xs = np.where(region[:, :, 0] > 200)
        w = xs.max() - xs.min() + 1
        h = ys.max() - ys.min() + 1
        assert 0.95 < h / w < 1.05, f"circle became {w}x{h}"


def test_low_end_profile_uses_lower_sampling_and_detection_resolution():
    from src.performance import get_profile
    lite = get_profile("lite")
    balanced = get_profile("balanced")
    assert lite.sample_fps < balanced.sample_fps
    assert lite.detection_width < balanced.detection_width
    assert lite.ffmpeg_threads == 2


def test_auto_profile_is_valid():
    from src.performance import get_profile
    assert get_profile("auto").name in {"lite", "balanced", "fast"}
