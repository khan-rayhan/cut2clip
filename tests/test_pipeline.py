"""End-to-end pipeline test on a synthetic clip."""

import subprocess
from pathlib import Path

from src.pipeline import process_clip


def _make_subject_video(path, duration=10):
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
    return [(int(w), int(h)) for w, h in
            (line.split(",") for line in out.strip().splitlines())]


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def test_process_clip_no_captions(tmp_path):
    src = tmp_path / "src.mp4"
    _make_subject_video(str(src))
    out = tmp_path / "vertical.mp4"
    process_clip(str(src), str(out), do_captions=False)
    assert (1080, 1920) in _dims(str(out))
    assert abs(_duration(str(out)) - 10.0) < 0.6


def test_process_clip_with_captions(tmp_path):
    """Full path including real transcription on CPU (tiny model).
    A pure tone transcribes to few or no words; the pipeline must
    still produce a correct vertical video."""
    src = tmp_path / "src.mp4"
    _make_subject_video(str(src))
    out = tmp_path / "vertical.mp4"
    process_clip(str(src), str(out), model="tiny")
    assert (1080, 1920) in _dims(str(out))
    assert abs(_duration(str(out)) - 10.0) < 0.6


def test_process_clip_output_on_other_filesystem(tmp_path):
    """Regression test: the pipeline's temp files live in /tmp
    (tmpfs) while the output folder is usually on the main disk.
    os.replace fails across filesystems ("Invalid cross-device
    link"), so the final move must copy instead. This test puts
    the output on the repo disk while the source sits in /tmp."""
    src = tmp_path / "src.mp4"
    _make_subject_video(str(src))
    out = Path(__file__).resolve().parent.parent / "tmp-cross-device-out.mp4"
    try:
        process_clip(str(src), str(out), do_captions=False)
        assert out.exists()
        assert (1080, 1920) in _dims(str(out))
        assert abs(_duration(str(out)) - 10.0) < 0.6
    finally:
        out.unlink(missing_ok=True)
