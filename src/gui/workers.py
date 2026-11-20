"""QThread workers for the GUI. Every long job runs here, never on
the GUI thread, and reports back through signals. A worker that
fails emits ``failed`` with a message; it never raises into Qt.
"""

from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QThread, Signal

from .. import highlights, ingestion
from ..live_monitor import LiveMonitor
from ..pipeline import process_clip


class ProbeWorker(QThread):
    finished_info = Signal(object)  # VideoInfo
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            self.finished_info.emit(ingestion.probe(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class ClipsWorker(QThread):
    finished_windows = Signal(list)  # list[ClipWindow]
    failed = Signal(str)

    def __init__(self, url: str, top_n: int = 5):
        super().__init__()
        self.url = url
        self.top_n = top_n

    def run(self) -> None:
        try:
            info = ingestion.probe(self.url)
            if info.duration is None:
                self.failed.emit("This URL is a live stream, not a VOD.")
                return
            windows = highlights.heatmap_windows(
                info.heatmap, info.duration, top_n=self.top_n)
            if windows:
                self.finished_windows.emit(windows)
                return
            fd, tmp = tempfile.mkstemp(suffix=".m4a")
            os.close(fd)
            try:
                ingestion.download_audio(self.url, tmp)
                caption_url = info.auto_caption_urls.get("en") or next(
                    iter(info.auto_caption_urls.values()), None)
                windows = highlights.combined_windows(
                    tmp, caption_url, info.duration, top_n=self.top_n)
                self.finished_windows.emit(windows)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        except Exception as exc:
            self.failed.emit(str(exc))


class VodClipWorker(QThread):
    """Download one highlight window, then run the Phase 3 pipeline
    on it. Emits progress lines for the log pane."""
    progress = Signal(str)
    finished_file = Signal(str)  # output path
    failed = Signal(str)

    def __init__(self, url: str, start: float, end: float,
                 out_path: str, model: str = "tiny"):
        super().__init__()
        self.url = url
        # Named window_start/window_end on purpose: ``start`` would
        # shadow QThread.start() and break the worker.
        self.window_start = start
        self.window_end = end
        self.out_path = out_path
        self.model = model

    def run(self) -> None:
        try:
            self.progress.emit(
                f"Downloading {self.window_start:.0f}-{self.window_end:.0f}s ...")
            fd, tmp = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            try:
                ingestion.download_section(self.url, self.window_start,
                                           self.window_end, tmp)
                self.progress.emit("Downloaded. Reframing and captioning ...")
                process_clip(tmp, self.out_path, model=self.model,
                             log=self.progress.emit)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            self.finished_file.emit(self.out_path)
        except Exception as exc:
            self.failed.emit(str(exc))


class LiveWorker(QThread):
    """Run the Phase 2 live monitor until stopped. Forwards spike
    and clip events to the GUI."""
    event = Signal(dict)
    failed = Signal(str)
    stopped = Signal()

    def __init__(self, url: str, out_dir: str, z_threshold: float = 2.5):
        super().__init__()
        self.url = url
        self.out_dir = out_dir
        self.z_threshold = z_threshold
        self._monitor: LiveMonitor | None = None

    def _on_event(self, event: dict) -> None:
        self.event.emit(event)

    def run(self) -> None:
        try:
            self._monitor = LiveMonitor(
                self.url, self.out_dir, z_threshold=self.z_threshold,
                on_event=self._on_event)
            self._monitor.run()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.stopped.emit()

    def stop(self) -> None:
        if self._monitor is not None:
            self._monitor._stop.set()
