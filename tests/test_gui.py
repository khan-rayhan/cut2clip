"""GUI tests, run offscreen (no display needed).

Workers are tested through their signals; the window is tested by
construction, settings round-trip, and the detect flow with a
mocked probe.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from unittest import mock

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from src.gui.main_window import MainWindow
from src.gui.workers import ClipsWorker, LiveWorker, ProbeWorker, VodClipWorker
from src.ingestion import HeatPoint, IngestionError, VideoInfo


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _wait_for(condition, timeout=15.0):
    """Pump Qt events until ``condition`` is true or the timeout hits."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _run_worker(worker):
    """Start a QThread worker and wait until it finishes."""
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    worker.start()
    loop.exec()
    worker.wait(2000)


def test_window_constructs(app):
    window = MainWindow(settings_org="ShortsAppTest", settings_app="Test1")
    assert window.url_edit is not None
    assert window.detect_button is not None
    assert window.windows_list is not None
    assert window.live_button is not None
    assert window.model_combo.count() == 3
    assert window.device_combo.count() == 3
    window.close()


def test_settings_roundtrip(app):
    org, name = "ShortsAppTest", "TestSettings"
    first = MainWindow(settings_org=org, settings_app=name)
    first.out_edit.setText("/tmp/test-clips")
    first.model_combo.setCurrentIndex(first.model_combo.findData("base"))
    first._save_settings()
    first.close()
    second = MainWindow(settings_org=org, settings_app=name)
    assert second.out_edit.text() == "/tmp/test-clips"
    assert second.model_combo.currentData() == "base"
    assert second.model_combo.currentText() == "Base"
    second.close()


def test_spike_threshold_level_label(app):
    """The level next to the spike threshold number follows the value:
    below 2.0 Low, 2.0–3.0 Medium, above 3.0 High."""
    from PySide6.QtCore import QSettings

    org, name = "ShortsAppTest", "TestZLevel"
    QSettings(org, name).clear()
    window = MainWindow(settings_org=org, settings_app=name)
    assert window.z_spin.value() == 2.5
    assert window.z_level_label.text() == "Medium"
    window.z_spin.setValue(1.5)
    assert window.z_level_label.text() == "Low"
    window.z_spin.setValue(4.0)
    assert window.z_level_label.text() == "High"
    window.close()


def test_probe_worker_invalid_url(app):
    received = {}
    worker = ProbeWorker("https://example.invalid/not-a-video")
    worker.finished_info.connect(lambda info: received.setdefault("info", info))
    worker.failed.connect(lambda msg: received.setdefault("error", msg))
    _run_worker(worker)
    assert "error" in received
    assert "info" not in received


def test_probe_worker_mocked(app):
    fake = VideoInfo(url="https://example.invalid/x", title="Fake Video",
                     duration=213.0, is_live=False, heatmap=[],
                     auto_caption_urls={})
    received = {}
    with mock.patch("src.ingestion.probe", return_value=fake):
        worker = ProbeWorker("https://example.invalid/x")
        worker.finished_info.connect(lambda info: received.setdefault("info", info))
        worker.failed.connect(lambda msg: received.setdefault("error", msg))
        _run_worker(worker)
    assert received.get("info") is fake
    assert "error" not in received


def test_vod_clip_worker_mocked(app, tmp_path):
    received = {}
    out_path = str(tmp_path / "clip.mp4")
    # Patch the names as the worker sees them: process_clip is
    # imported into the workers module, so patching src.pipeline
    # would not affect the worker's reference.
    with mock.patch("src.gui.workers.ingestion.download_section",
                    return_value="/tmp/fake.mp4") as dl, \
         mock.patch("src.gui.workers.process_clip",
                    return_value=out_path) as proc:
        worker = VodClipWorker("https://example.invalid/x", 20.0, 60.0,
                               out_path, model="tiny")
        worker.finished_file.connect(lambda p: received.setdefault("file", p))
        worker.failed.connect(lambda msg: received.setdefault("error", msg))
        _run_worker(worker)
    assert received.get("file") == out_path
    assert "error" not in received
    assert dl.called and proc.called


def test_live_worker_invalid_url(app, tmp_path):
    received = {}
    worker = LiveWorker("https://example.invalid/not-live", str(tmp_path))
    worker.failed.connect(lambda msg: received.setdefault("error", msg))
    worker.event.connect(lambda e: received.setdefault("event", e))
    _run_worker(worker)
    assert "error" in received


def test_window_detect_invalid_url(app):
    window = MainWindow(settings_org="ShortsAppTest", settings_app="Test2")
    window.url_edit.setText("https://example.invalid/not-a-video")
    window._on_detect()
    ok = _wait_for(lambda: "Could not detect" in window.info_label.text(),
                   timeout=20.0)
    assert ok, f"status stayed: {window.info_label.text()}"
    window.close()


def test_caption_combo_and_roundtrip(app):
    from PySide6.QtCore import QSettings

    org, name = "ShortsAppTest", "TestCaptionStyle"
    QSettings(org, name).clear()  # a previous run saved "neon" here
    first = MainWindow(settings_org=org, settings_app=name)
    assert first.caption_combo.count() == 4
    assert [first.caption_combo.itemText(i) for i in range(4)] == [
        "Hormozi", "TikTok", "Karaoke", "Neon"]
    assert first.caption_combo.currentData() == "hormozi"
    assert first.caption_combo.currentText() == "Hormozi"
    first.caption_combo.setCurrentIndex(first.caption_combo.findData("neon"))
    first._save_settings()
    first.close()
    second = MainWindow(settings_org=org, settings_app=name)
    assert second.caption_combo.currentData() == "neon"
    assert second.caption_combo.currentText() == "Neon"
    second.close()


def test_auto_top3_processes_first_three_windows(app, tmp_path):
    """Auto-clip top 3 queues exactly the first three windows,
    ignoring the checkboxes, and finishes them all."""
    from PySide6.QtCore import QThread, Signal

    from src.highlights import ClipWindow

    class FakeWorker(QThread):
        progress = Signal(str)
        progress_pct = Signal(int, str)
        finished_file = Signal(str)
        failed = Signal(str)
        created = []

        def __init__(self, url, start, end, out_path, model="tiny",
                     caption_style="hormozi", device="auto",
                     performance_mode="auto"):
            super().__init__()
            self.out_path = out_path
            FakeWorker.created.append(caption_style)

        def run(self):
            self.finished_file.emit(self.out_path)

    window = MainWindow(settings_org="ShortsAppTest", settings_app="TestAuto3")
    window.out_edit.setText(str(tmp_path))
    window._current_url = "https://example.invalid/x"
    window.caption_combo.setCurrentIndex(
        window.caption_combo.findData("tiktok"))
    windows = [ClipWindow(start=float(10 + 40 * i), end=float(50 + 40 * i),
                          peak_time=float(30 + 40 * i), score=0.9 - 0.1 * i,
                          source="heatmap") for i in range(5)]
    window._on_windows(windows)
    assert window.auto_button.isEnabled()
    with mock.patch("src.gui.main_window.VodClipWorker", FakeWorker):
        window._on_auto_top3()
        ok = _wait_for(lambda: window.outputs_list.count() == 3, timeout=10.0)
    assert ok, f"outputs: {window.outputs_list.count()}"
    assert window.auto_button.isEnabled()  # re-enabled when done
    # The caption style picked in settings reached every worker.
    assert FakeWorker.created == ["tiktok"] * 3
    # Only the first three windows were processed, in order.
    stamps = [window.outputs_list.item(i).text() for i in range(3)]
    assert stamps[0].endswith("clip-00-10.mp4")
    assert stamps[1].endswith("clip-00-50.mp4")
    assert stamps[2].endswith("clip-01-30.mp4")
    window.close()


def test_clips_worker_falls_back_when_comments_fail(app):
    """Comments disabled/unavailable must not break detection:
    the worker falls back to the heatmap alone."""
    fake = VideoInfo(url="https://example.invalid/x", title="Fake Video",
                     duration=180.0, is_live=False,
                     heatmap=[HeatPoint(58, 60, 1.0),
                              HeatPoint(60, 62, 0.9),
                              HeatPoint(138, 140, 0.8)],
                     auto_caption_urls={})
    received = {}
    with mock.patch("src.ingestion.probe", return_value=fake), \
         mock.patch("src.ingestion.fetch_comments",
                    side_effect=IngestionError("comments disabled")):
        worker = ClipsWorker("https://example.invalid/x")
        worker.finished_windows.connect(
            lambda w: received.setdefault("windows", w))
        worker.failed.connect(lambda msg: received.setdefault("error", msg))
        _run_worker(worker)
    assert "error" not in received
    assert received["windows"]
    assert all(w.source == "heatmap" for w in received["windows"])


def test_clips_worker_uses_audio_transcript_fallback_without_heatmap(app):
    from src.highlights import ClipWindow

    fake = VideoInfo(url="https://example.invalid/x", title="No Heatmap",
                     duration=180.0, is_live=False, heatmap=[],
                     auto_caption_urls={"en": "https://example.invalid/captions.json3"})
    expected = [ClipWindow(start=20.0, end=60.0, peak_time=40.0,
                           score=0.9, source="audio+transcript")]
    received = {}
    with mock.patch("src.ingestion.probe", return_value=fake), \
         mock.patch("src.ingestion.fetch_comment_points", return_value=(None, 0)), \
         mock.patch("src.ingestion.audio_stream_source",
                    return_value=("https://example.invalid/audio", {"User-Agent": "test"})), \
         mock.patch("src.gui.workers.highlights.combined_windows",
                    return_value=expected) as fallback:
        worker = ClipsWorker(fake.url)
        worker.finished_windows.connect(lambda windows: received.setdefault("windows", windows))
        worker.failed.connect(lambda message: received.setdefault("error", message))
        _run_worker(worker)
    assert received.get("windows") == expected
    assert "error" not in received
    fallback.assert_called_once_with(
        "https://example.invalid/audio", fake.auto_caption_urls["en"],
        180.0, top_n=5, audio_headers={"User-Agent": "test"})


def test_existing_clip_output_is_not_overwritten(tmp_path):
    from src.gui.main_window import _unused_output_path

    original = tmp_path / "clip-00-20.mp4"
    original.write_bytes(b"previous export")
    second = _unused_output_path(str(original))
    assert second.endswith("clip-00-20-2.mp4")
    assert original.read_bytes() == b"previous export"
