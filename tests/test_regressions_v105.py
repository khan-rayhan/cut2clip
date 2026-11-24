"""Regression tests for the v1.0.5 bug fixes (one group per fix)."""

import os
import subprocess
import sys
import threading
import time
import types

import numpy as np
import pytest

from src import captions, highlights, ingestion, live_monitor
from src.highlights import ClipWindow, parse_comment_timestamps, select_windows
from src.live_monitor import LiveMonitor


def _make_video(path, size="640x360", rate=25, duration=1):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"color=c=gray:size={size}:rate={rate}:duration={duration}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


# ------------------------------------------------------------- captions

def test_ass_time_never_rounds_up_to_sixty_seconds():
    assert captions._ass_time(59.996) == "0:01:00.00"
    assert captions._ass_time(3599.999) == "1:00:00.00"
    assert ":60." not in captions._ass_time(119.9951)


def test_words_are_trimmed_and_sanitised_for_ass(tmp_path):
    out = tmp_path / "c.ass"
    captions.words_to_ass([(0.0, 1.3, "a{b}"), (1.25, 2.0, "c\\d")], str(out))
    text = out.read_text(encoding="utf-8")
    dialogue = [l for l in text.splitlines() if l.startswith("Dialogue")]
    assert dialogue[0].split(",")[2] == "0:00:01.25"   # trimmed to next start
    assert "a(b)" in text and "cd" in text             # no stray override tags
    assert "{b}" not in text


# ------------------------------------------------------------- ingestion

def test_download_section_forces_overwrite_and_rejects_empty_file(tmp_path, monkeypatch):
    seen = {}

    def fake(url, opts, download):
        seen["overwrites"] = opts.get("overwrites")
        open(opts["outtmpl"], "wb").close()  # yt-dlp "finished" with 0 bytes
        return {}

    monkeypatch.setattr(ingestion, "_extract", fake)
    out = str(tmp_path / "clip.mp4")
    with pytest.raises(ingestion.IngestionError, match="empty"):
        ingestion.download_section("u", 10, 50, out)
    assert seen["overwrites"] is True
    assert not os.path.exists(out)


def test_ytdlp_replaces_a_placeholder_file_when_overwrites_is_on(tmp_path):
    """Real yt-dlp against a local HTTP server: an empty placeholder
    must not make it skip the download."""
    import functools
    import http.server

    import yt_dlp

    _make_video(tmp_path / "sample.mp4", duration=6)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(tmp_path))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/sample.mp4"
        dest = tmp_path / "section.mp4"
        dest.write_bytes(b"")  # what mkstemp used to leave behind
        opts = {"quiet": True, "no_warnings": True, "format": "b",
                "outtmpl": str(dest), "overwrites": True,
                "download_ranges": lambda i, y: [{"start_time": 1, "end_time": 4}],
                "force_keyframes_at_cuts": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
        assert dest.stat().st_size > 0
    finally:
        server.shutdown()


# ------------------------------------------------------------- highlights

def test_select_windows_replaces_a_peak_dropped_for_overlap():
    # The 2nd and 3rd peaks overlap the first once clamped; the 4th is free.
    peaks = [(5.0, 1.0), (30.0, 0.9), (45.0, 0.8), (80.0, 0.7)]
    windows = select_windows(peaks, 100.0, top_n=2)
    assert [(w.start, w.end) for w in windows] == [(0.0, 40.0), (60.0, 100.0)]


def test_heatmap_windows_still_offers_top_n_near_the_edges():
    from src.ingestion import HeatPoint
    values = [0.2, 1.0, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2,
              0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]
    # a rival peak 40 s later (allowed by min_gap) whose window overlaps
    values[5] = 0.95
    values[16] = 0.6
    heat = [HeatPoint(i * 10.0, (i + 1) * 10.0, v) for i, v in enumerate(values)]
    windows = highlights.heatmap_windows(heat, 200.0, top_n=2)
    assert len(windows) == 2
    assert windows[0].end <= windows[1].start


def test_invalid_comment_timestamps_are_ignored():
    assert parse_comment_timestamps("3:75 then 1:90:00 then 2:30") == [150.0]


# ------------------------------------------------------------- GUI worker

def test_vod_worker_downloads_into_a_fresh_path(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from unittest import mock

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from src.gui.workers import VodClipWorker

    QApplication.instance() or QApplication([])
    seen = {}

    def fake_download(url, start, end, path, progress_cb=None):
        seen["existed"] = os.path.exists(path)   # must NOT pre-exist
        with open(path, "wb") as fh:
            fh.write(b"x")
        return path

    out = str(tmp_path / "clip.mp4")
    worker = VodClipWorker("u", 0.0, 40.0, out)
    done = {}
    worker.finished_file.connect(lambda p: done.setdefault("ok", p))
    worker.failed.connect(lambda m: done.setdefault("err", m))
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    with mock.patch("src.gui.workers.ingestion.download_section", fake_download), \
         mock.patch("src.gui.workers.process_clip", return_value=out):
        worker.start()
        loop.exec()
        worker.wait(2000)
    assert done.get("ok") == out, done
    assert seen["existed"] is False


# ------------------------------------------------------------- ring buffer

def _fake_streamlink(monkeypatch, streams):
    fake = types.ModuleType("streamlink")

    class Session:
        def streams(self, url):
            return streams

    fake.Streamlink = Session
    monkeypatch.setitem(sys.modules, "streamlink", fake)


def test_muxed_streamlink_stream_falls_back_to_ytdlp(monkeypatch):
    from src.ring_buffer import resolve_stream_url

    class Muxed:                       # no .url, like MuxedHLSStream
        def to_url(self):
            raise TypeError("cannot be translated to a URL")

    _fake_streamlink(monkeypatch, {"best": Muxed()})
    monkeypatch.setattr("src.ring_buffer._resolve_with_ytdlp",
                        lambda url: "https://example.invalid/fallback.m3u8")
    assert resolve_stream_url("https://example.invalid/live") == \
        "https://example.invalid/fallback.m3u8"


def test_m3u8_url_with_query_string_is_used_directly(monkeypatch):
    from src.ring_buffer import resolve_stream_url
    _fake_streamlink(monkeypatch, {})
    url = "https://cdn.example/live/index.m3u8?token=abc"
    assert resolve_stream_url(url) == url


def test_extract_clip_survives_an_apostrophe_in_the_folder_name(tmp_path):
    import datetime

    from src.ring_buffer import RingBuffer

    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=320x180:rate=25:duration=30", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=30", "-shortest", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True)
    seg_dir = tmp_path / "it's a buffer"
    seg_dir.mkdir()
    base = datetime.datetime(2026, 11, 18, 12, 0, 0).timestamp()
    for i in range(3):
        stamp = datetime.datetime.fromtimestamp(base + i * 10).strftime("%Y%m%dT%H%M%S")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(i * 10), "-i", str(src),
             "-t", "10", "-c", "copy", str(seg_dir / f"seg-{stamp}.ts")], check=True)
    buf = RingBuffer(str(src), str(seg_dir))
    first = buf._segments()[0][0]
    out = tmp_path / "clip.mp4"
    buf.extract_clip(first + 5, first + 25, str(out))
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(out)], text=True))
    assert abs(dur - 20.0) < 0.6


# ------------------------------------------------------------- live monitor

class _FlakyBuffer:
    """First cut fails with a non-RingBufferError, later cuts work."""

    def __init__(self):
        self.calls = 0

    def extract_clip(self, start, end, out_path):
        self.calls += 1
        if self.calls == 1:
            raise OSError("disk hiccup")
        with open(out_path, "wb") as fh:
            fh.write(b"raw")
        return out_path

    def stop(self):
        pass


def test_clip_worker_survives_an_unexpected_error(tmp_path):
    out_dir = tmp_path / "clips"
    os.makedirs(out_dir)
    monitor = LiveMonitor("u", str(out_dir), process=False)
    monitor.buffer = _FlakyBuffer()
    now = time.time()
    first, second = str(out_dir / "a.mp4"), str(out_dir / "b.mp4")
    monitor._pending += [(now - 100, now - 60, first), (now - 100, now - 60, second)]
    clip_thread, proc_thread = monitor._start_workers()
    monitor._stop.set()
    clip_thread.join(timeout=15)
    assert monitor.clips_saved == [second]


def test_spike_check_is_throttled_but_every_message_is_counted():
    monitor = LiveMonitor("u", "unused", process=False)
    counts = {"feed": 0, "check": 0}
    real_feed, real_check = monitor.velocity.feed, monitor.velocity.check

    def feed(ts=None):
        counts["feed"] += 1
        return real_feed(ts)

    def check(now=None):
        counts["check"] += 1
        return real_check(now)

    monitor.velocity.feed, monitor.velocity.check = feed, check
    monitor._chat_loop(iter([{"text": "hi"}] * 500))
    assert counts["feed"] == 500
    assert counts["check"] <= 3


def test_chat_ending_is_reported():
    events = []
    monitor = LiveMonitor("u", "unused", process=False, on_event=events.append)
    monitor._chat_loop(iter([]))
    assert any("chat ended" in e.get("text", "").lower() for e in events)


def test_dead_recorder_is_restarted_then_monitor_gives_up(tmp_path, monkeypatch):
    monkeypatch.setattr(live_monitor, "RECORDER_RETRY_DELAY_S", 0.1)
    monkeypatch.setattr(live_monitor, "RECORDER_MAX_RESTARTS", 1)
    src = tmp_path / "short.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "testsrc2=size=320x180:rate=25:duration=2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(src)], check=True)
    events = []
    monitor = LiveMonitor("u", str(tmp_path / "out"), process=False,
                          on_event=events.append)
    started = time.time()
    monitor.run(duration_s=60, chat_iter=iter([]), stream_source=str(src))
    texts = [e.get("text", "") for e in events]
    assert any("reconnecting" in t for t in texts), texts
    assert any("Stopping" in t for t in texts), texts
    assert time.time() - started < 40          # gave up on its own


# ------------------------------------------------------------- framing

def test_trajectory_uses_the_real_sample_rate(tmp_path):
    from src.framing import Framer

    src = tmp_path / "v.mp4"
    _make_video(src, rate=25)
    framer = Framer(str(src), sample_fps=2.0)
    assert framer.step == 12                      # round(25 / 2), banker's rounding
    framer.centers = [float(i * 100) for i in range(10)]
    # t = 1 s is sample 25 / 12 = 2.083, not 2.0
    assert framer._center_at(1.0) == pytest.approx(208.33, abs=0.1)


def test_narrow_portrait_source_is_cropped_not_stretched(tmp_path):
    import cv2

    from src.framing import Framer

    src = tmp_path / "tall.mp4"
    _make_video(src, size="540x1200", rate=5)     # taller than 9:16
    framer = Framer(str(src))
    framer.centers = [270.0, 270.0]
    frame = np.full((1200, 540, 3), 40, np.uint8)
    cv2.circle(frame, (270, 600), 150, (255, 255, 255), -1)
    out = framer._reframe_frame(frame, 0.0)
    assert out.shape == (1920, 1080, 3)
    ys, xs = np.where(out[:, :, 0] > 200)
    ratio = (ys.max() - ys.min() + 1) / (xs.max() - xs.min() + 1)
    assert 0.95 < ratio < 1.05, f"circle became {ratio:.2f} tall-to-wide"
