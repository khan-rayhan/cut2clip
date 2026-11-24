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


import pytest


@pytest.mark.model_integration
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


def test_process_clip_reframe_and_captions_single_output_encode(tmp_path, monkeypatch):
    from src import captions

    src = tmp_path / "src.mp4"
    _make_subject_video(str(src), duration=2)
    out = tmp_path / "captioned-vertical.mp4"
    monkeypatch.setattr(captions, "transcribe_words",
                        lambda *a, **k: [(0.1, 0.8, "hello")])
    process_clip(str(src), str(out), do_captions=True, performance_mode="lite")
    assert (1080, 1920) in _dims(str(out))
    assert abs(_duration(str(out)) - 2.0) < 0.6
    streams = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(out)], text=True).splitlines()
    assert "audio" in streams


def test_process_clip_reports_progress(tmp_path):
    src = tmp_path / "src.mp4"
    _make_subject_video(str(src))
    out = tmp_path / "vertical.mp4"
    seen: list[tuple[float, str]] = []
    process_clip(str(src), str(out), do_captions=False,
                 progress_cb=lambda frac, label: seen.append((frac, label)))
    assert out.exists()
    assert seen, "progress_cb was never called"
    fracs = [f for f, _ in seen]
    assert all(0.0 <= f <= 1.0 for f in fracs)
    assert fracs == sorted(fracs), "progress must not go backwards"
    assert fracs[0] <= 0.05
    assert fracs[-1] == 1.0
    # Frame-by-frame encode progress, not just start/end markers.
    assert len(set(fracs)) > 10
    assert any("Reframing" in label for _, label in seen)


def test_noop_pipeline_copies_and_preserves_original(tmp_path):
    import hashlib

    src = tmp_path / "original.mp4"
    _make_subject_video(str(src), duration=1)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    out = tmp_path / "copy.mp4"
    process_clip(str(src), str(out), do_reframe=False, do_captions=False)
    assert src.exists()
    assert out.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    assert hashlib.sha256(out.read_bytes()).hexdigest() == before


def test_noop_pipeline_same_path_is_safe(tmp_path):
    src = tmp_path / "original.mp4"
    _make_subject_video(str(src), duration=1)
    before = src.read_bytes()
    result = process_clip(str(src), str(src), do_reframe=False, do_captions=False)
    assert result == str(src)
    assert src.read_bytes() == before


def test_processed_pipeline_rejects_same_input_output_path(tmp_path):
    import pytest

    src = tmp_path / "original.mp4"
    _make_subject_video(str(src), duration=1)
    before = src.read_bytes()
    with pytest.raises(ValueError, match="must be different"):
        process_clip(str(src), str(src), do_reframe=True, do_captions=False)
    assert src.read_bytes() == before
