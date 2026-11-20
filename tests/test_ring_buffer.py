"""Tests for the rolling ring buffer.

The live test records a local file in real time, so it takes about
75 seconds. The extraction test builds segments offline and is fast.
"""

import os
import subprocess
import time

import pytest

from src.ring_buffer import RingBuffer


def _make_test_video(path, duration=120):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", path],
        check=True)


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def test_extract_clip_from_segments(tmp_path):
    src = tmp_path / "src.mp4"
    _make_test_video(str(src))
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    # Build 12 ten-second segments offline, named by wall-clock start
    # time ten seconds apart. (The live segmenter names files the same
    # way; cutting the whole file at once would stamp every segment
    # with the same second, so the cuts are made one by one.)
    import datetime
    base = datetime.datetime(2026, 11, 18, 12, 0, 0,
                             tzinfo=datetime.timezone.utc).timestamp()
    for i in range(12):
        stamp = datetime.datetime.fromtimestamp(
            base + i * 10, tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-ss", str(i * 10), "-i", str(src), "-t", "10",
             "-c", "copy", str(seg_dir / f"seg-{stamp}.ts")],
            check=True)
    buf = RingBuffer(str(src), str(seg_dir))
    segments = buf._segments()
    assert len(segments) == 12
    # Ask for the window in the buffer's own clock (the parsed segment
    # times), the same clock production uses.
    first = segments[0][0]
    out = tmp_path / "clip.mp4"
    buf.extract_clip(first + 25, first + 65, str(out))
    assert abs(_duration(str(out)) - 40.0) < 0.6


def test_ring_buffer_live(tmp_path):
    src = tmp_path / "src.mp4"
    _make_test_video(str(src), duration=120)
    seg_dir = tmp_path / "segs"
    buf = RingBuffer(str(src), str(seg_dir), segment_time=5, keep_segments=16)
    buf.start()
    try:
        time.sleep(70)
        earliest, latest = buf.available_range()
        assert earliest is not None and latest is not None
        assert latest - earliest >= 60  # at least 60s retained
        out = tmp_path / "clip.mp4"
        now = time.time()
        buf.extract_clip(now - 40, now, str(out))
        assert abs(_duration(str(out)) - 40.0) < 0.6
    finally:
        buf.stop()
