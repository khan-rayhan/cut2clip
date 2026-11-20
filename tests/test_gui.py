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
from src.gui.workers import LiveWorker, ProbeWorker, VodClipWorker
from src.ingestion import VideoInfo


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
    first.model_combo.setCurrentText("base")
    first._save_settings()
    first.close()
    second = MainWindow(settings_org=org, settings_app=name)
    assert second.out_edit.text() == "/tmp/test-clips"
    assert second.model_combo.currentText() == "base"
    second.close()


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
