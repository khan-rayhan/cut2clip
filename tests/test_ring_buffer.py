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


def test_recorder_stderr_is_captured_when_ffmpeg_fails(tmp_path):
    """Regression: on a real Windows test (2026-11-24) the recorder
    died with "ffmpeg exit 4294967295" and no reason, because the
    windowed bundle swallows the recorder's stderr. The tail must
    be kept so the live log can name the failure."""
    buf = RingBuffer("http://127.0.0.1:9/nope.m3u8", str(tmp_path / "segs"))
    buf.start()
    try:
        for _ in range(100):
            if not buf.is_running():
                break
            time.sleep(0.1)
        assert not buf.is_running()
        assert buf.exit_code is not None
        assert "Connection refused" in buf.last_stderr()
    finally:
        buf.stop()


@pytest.mark.slow
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


# ------------------------------------------------------- stream URL resolving

def _broken_streamlink(monkeypatch):
    """Replace the ``streamlink`` module with one whose session
    always fails, as it did for the YouTube live URL on 2026-11-20.
    Works whether or not streamlink is installed in this venv."""
    import sys
    import types

    fake = types.ModuleType("streamlink")

    class BrokenSession:
        def streams(self, url):
            raise RuntimeError("No plugin can handle URL")

    fake.Streamlink = BrokenSession
    monkeypatch.setitem(sys.modules, "streamlink", fake)


def test_resolve_falls_back_to_ytdlp_when_streamlink_fails(monkeypatch):
    from src.ring_buffer import resolve_stream_url

    _broken_streamlink(monkeypatch)
    monkeypatch.setattr(
        "src.ring_buffer._resolve_with_ytdlp",
        lambda url: "https://example.invalid/live.m3u8")
    assert resolve_stream_url("https://www.youtube.com/live/OIeLbmyraRQ") == \
        "https://example.invalid/live.m3u8"


def test_resolve_error_names_both_failures(monkeypatch):
    from src.ring_buffer import RingBufferError, resolve_stream_url

    _broken_streamlink(monkeypatch)

    def boom(url):
        raise RuntimeError("yt-dlp: ERROR: Video unavailable")

    monkeypatch.setattr("src.ring_buffer._resolve_with_ytdlp", boom)
    with pytest.raises(RingBufferError) as excinfo:
        resolve_stream_url("https://www.youtube.com/live/OIeLbmyraRQ")
    msg = str(excinfo.value)
    assert "streamlink failed: No plugin can handle URL" in msg
    assert "yt-dlp fallback also failed" in msg
    assert "yt-dlp: ERROR: Video unavailable" in msg


def test_ytdlp_fallback_prefers_hls_format(monkeypatch):
    from src.ring_buffer import _resolve_with_ytdlp

    def fake_extract(url, opts, download):
        return {"formats": [
            {"ext": "mp4", "protocol": "https",
             "url": "https://example.invalid/video.mp4"},
            {"ext": "m3u8", "protocol": "m3u8_native",
             "url": "https://example.invalid/low.m3u8"},
            {"ext": "m3u8", "protocol": "m3u8_native",
             "url": "https://example.invalid/best.m3u8"},
        ], "url": "https://example.invalid/video.mp4"}

    monkeypatch.setattr("src.ingestion._extract", fake_extract)
    # The last (best) HLS format wins.
    assert _resolve_with_ytdlp("https://www.youtube.com/live/x") == \
        "https://example.invalid/best.m3u8"


def test_ytdlp_fallback_uses_direct_url_without_hls(monkeypatch):
    from src.ring_buffer import _resolve_with_ytdlp

    def fake_extract(url, opts, download):
        return {"formats": [
            {"ext": "mp4", "protocol": "https",
             "url": "https://example.invalid/video.mp4"},
        ], "url": "https://example.invalid/video.mp4"}

    monkeypatch.setattr("src.ingestion._extract", fake_extract)
    assert _resolve_with_ytdlp("https://www.youtube.com/live/x") == \
        "https://example.invalid/video.mp4"


def test_resolve_passes_m3u8_through(monkeypatch):
    from src.ring_buffer import resolve_stream_url

    # No resolver is even consulted for a direct .m3u8 URL.
    _broken_streamlink(monkeypatch)
    assert resolve_stream_url("https://example.invalid/stream.m3u8") == \
        "https://example.invalid/stream.m3u8"
