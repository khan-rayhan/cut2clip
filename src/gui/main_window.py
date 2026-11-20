"""Main window: paste a URL, detect VOD or live, get clips."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QDoubleSpinBox, QTabWidget,
    QVBoxLayout, QWidget)

from .. import highlights
from .workers import ClipsWorker, LiveWorker, ProbeWorker, VodClipWorker

ORG = "ShortsApp"
APP = "ShortsApp"


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _repolish(widget) -> None:
    """Re-apply the style sheet after an objectName change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class MainWindow(QMainWindow):
    def __init__(self, settings_org: str = ORG, settings_app: str = APP):
        super().__init__()
        from .. import __version__
        self.setWindowTitle(f"Shorts App v{__version__} — 40-second vertical clips")
        self.resize(760, 560)
        self.settings = QSettings(settings_org, settings_app)
        self._workers: list = []
        self._windows: list[highlights.ClipWindow] = []
        self._live_worker: LiveWorker | None = None
        self._build_ui()
        self._load_settings()

    # ------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        hero = QLabel("▶  Shorts App  •  40-second vertical Shorts & Reels")
        hero.setObjectName("hero")
        layout.addWidget(hero)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a YouTube / Twitch / Facebook URL ...")
        self.detect_button = QPushButton("Detect")
        self.detect_button.setObjectName("primary")
        self.detect_button.clicked.connect(self._on_detect)
        url_row.addWidget(self.url_edit)
        url_row.addWidget(self.detect_button)
        layout.addLayout(url_row)

        self.info_label = QLabel("Paste a URL and press Detect.")
        self.info_label.setObjectName("info")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.tabs = QTabWidget()

        vod_tab = QWidget()
        vod_layout = QVBoxLayout(vod_tab)
        self.windows_list = QListWidget()
        vod_layout.addWidget(self.windows_list)
        vod_buttons = QHBoxLayout()
        self.process_button = QPushButton("Process selected")
        self.process_button.setObjectName("primary")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self._on_process_selected)
        vod_buttons.addWidget(self.process_button)
        self.vod_progress = QProgressBar()
        self.vod_progress.setVisible(False)
        vod_buttons.addWidget(self.vod_progress)
        vod_layout.addLayout(vod_buttons)
        self.tabs.addTab(vod_tab, "VOD clips")

        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)
        live_controls = QHBoxLayout()
        live_controls.addWidget(QLabel("Z threshold:"))
        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(1.0, 5.0)
        self.z_spin.setSingleStep(0.5)
        self.z_spin.setValue(2.5)
        live_controls.addWidget(self.z_spin)
        self.live_button = QPushButton("Start monitoring")
        self.live_button.setObjectName("accent")
        self.live_button.setEnabled(False)
        self.live_button.clicked.connect(self._on_live_toggle)
        live_controls.addWidget(self.live_button)
        live_controls.addStretch()
        live_layout.addLayout(live_controls)
        self.live_log = QPlainTextEdit()
        self.live_log.setReadOnly(True)
        live_layout.addWidget(self.live_log)
        self.live_clips = QListWidget()
        live_layout.addWidget(self.live_clips)
        self.tabs.addTab(live_tab, "Live monitor")

        layout.addWidget(self.tabs)

        self.outputs_list = QListWidget()
        self.outputs_list.itemDoubleClicked.connect(self._on_open_output)
        layout.addWidget(QLabel("Finished clips (double-click to open):"))
        layout.addWidget(self.outputs_list)

        settings_row = QHBoxLayout()
        settings_row.addWidget(QLabel("Output folder:"))
        self.out_edit = QLineEdit()
        settings_row.addWidget(self.out_edit)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._on_browse_out)
        settings_row.addWidget(browse)
        settings_row.addWidget(QLabel("Whisper model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small"])
        settings_row.addWidget(self.model_combo)
        settings_row.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(["auto", "cpu", "cuda"])
        settings_row.addWidget(self.device_combo)
        layout.addLayout(settings_row)

        self.statusBar().showMessage("Ready.")
        self.setCentralWidget(central)

    # ------------------------------------------------------------ settings

    def _load_settings(self) -> None:
        self.out_edit.setText(self.settings.value(
            "output_folder", os.path.join(os.path.expanduser("~"), "ShortsClips")))
        self.model_combo.setCurrentText(self.settings.value("model", "tiny"))
        self.device_combo.setCurrentText(self.settings.value("device", "auto"))
        self.z_spin.setValue(float(self.settings.value("z_threshold", 2.5)))

    def _save_settings(self) -> None:
        self.settings.setValue("output_folder", self.out_edit.text())
        self.settings.setValue("model", self.model_combo.currentText())
        self.settings.setValue("device", self.device_combo.currentText())
        self.settings.setValue("z_threshold", self.z_spin.value())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._save_settings()
        self._stop_live(abort=True)
        super().closeEvent(event)

    # ------------------------------------------------------------ detect

    def _on_detect(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Paste a video URL first.")
            return
        self.detect_button.setEnabled(False)
        self.info_label.setText("Detecting ...")
        self._current_url = url
        worker = ProbeWorker(url)
        worker.finished_info.connect(self._on_detected)
        worker.failed.connect(self._on_detect_failed)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _on_detected(self, info) -> None:
        self.detect_button.setEnabled(True)
        kind = "LIVE" if info.is_live else "VOD"
        heat = f", heatmap {len(info.heatmap)} points" if info.has_heatmap else ", no heatmap"
        dur = _fmt(info.duration) if info.duration else "live"
        self.info_label.setText(f"{info.title or '(no title)'} — {kind}, {dur}{heat}")
        if info.is_live:
            self.live_button.setEnabled(True)
            self.tabs.setCurrentIndex(1)
            self.statusBar().showMessage("Live stream detected. Start monitoring when ready.")
        else:
            self._load_windows()

    def _on_detect_failed(self, message: str) -> None:
        self.detect_button.setEnabled(True)
        self.info_label.setText(f"Could not detect: {message}")
        self.statusBar().showMessage("Detection failed.")

    def _load_windows(self) -> None:
        self.statusBar().showMessage("Finding highlight windows ...")
        worker = ClipsWorker(self._current_url, top_n=5)
        worker.finished_windows.connect(self._on_windows)
        worker.failed.connect(self._on_detect_failed)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _on_windows(self, windows: list) -> None:
        self._windows = windows
        self.windows_list.clear()
        for i, w in enumerate(windows, 1):
            item = QListWidgetItem(
                f"#{i}  {_fmt(w.start)} - {_fmt(w.end)}  "
                f"peak {_fmt(w.peak_time)}  score {w.score:.2f}  [{w.source}]")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.windows_list.addItem(item)
        self.process_button.setEnabled(bool(windows))
        self.statusBar().showMessage(f"{len(windows)} highlight windows found.")

    # ------------------------------------------------------------ VOD process

    def _on_process_selected(self) -> None:
        selected = [self._windows[i] for i in range(self.windows_list.count())
                    if self.windows_list.item(i).checkState() == Qt.CheckState.Checked]
        if not selected:
            QMessageBox.warning(self, "Nothing selected", "Tick at least one window.")
            return
        out_dir = self.out_edit.text().strip()
        os.makedirs(out_dir, exist_ok=True)
        self.process_button.setEnabled(False)
        self.vod_progress.setVisible(True)
        self.vod_progress.setMaximum(len(selected))
        self.vod_progress.setValue(0)
        self._pending = list(selected)
        self._process_next()

    def _process_next(self) -> None:
        if not self._pending:
            self.process_button.setEnabled(True)
            self.vod_progress.setVisible(False)
            self.statusBar().showMessage("All selected clips processed.")
            return
        window = self._pending.pop(0)
        stamp = _fmt(window.start).replace(":", "-")
        out_path = os.path.join(self.out_edit.text().strip(),
                                f"clip-{stamp}.mp4")
        worker = VodClipWorker(self._current_url, window.start, window.end,
                               out_path, model=self.model_combo.currentText())
        worker.progress.connect(self.statusBar().showMessage)
        worker.finished_file.connect(self._on_clip_done)
        worker.failed.connect(self._on_clip_failed)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _on_clip_done(self, path: str) -> None:
        self.outputs_list.addItem(path)
        self.vod_progress.setValue(self.vod_progress.value() + 1)
        self._process_next()

    def _on_clip_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Clip failed", message)
        self.vod_progress.setValue(self.vod_progress.value() + 1)
        self._process_next()

    def _on_open_output(self, item: QListWidgetItem) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(item.text()))

    # ------------------------------------------------------------ live

    def _on_live_toggle(self) -> None:
        if self._live_worker is not None:
            self._stop_live()
            return
        out_dir = self.out_edit.text().strip()
        os.makedirs(out_dir, exist_ok=True)
        self._live_worker = LiveWorker(self._current_url, out_dir,
                                       z_threshold=self.z_spin.value(),
                                       model=self.model_combo.currentText())
        self._live_worker.event.connect(self._on_live_event)
        self._live_worker.failed.connect(self._on_live_failed)
        self._live_worker.stopped.connect(self._on_live_stopped)
        self._live_worker.start()
        self.live_button.setObjectName("danger")
        _repolish(self.live_button)
        self.live_button.setText("Stop monitoring")
        self.live_log.appendPlainText("Monitoring started.")
        self.statusBar().showMessage("Monitoring live chat ...")

    def _on_live_event(self, event: dict) -> None:
        if event["type"] == "spike":
            self.live_log.appendPlainText(
                f"SPIKE {event['time']}  z={event['z']:.1f}  "
                f"{event['count']} msgs/10s")
        elif event["type"] == "status":
            self.live_log.appendPlainText(event["text"])
        elif event["type"] == "clip":
            self.live_clips.addItem(event["path"])
            self.outputs_list.addItem(event["path"])
            self.live_log.appendPlainText(f"Saved {event['path']}")

    def _on_live_failed(self, message: str) -> None:
        self.live_log.appendPlainText(f"Monitor failed: {message}")

    def _on_live_stopped(self) -> None:
        self._live_worker = None
        self.live_button.setEnabled(True)
        self.live_button.setObjectName("accent")
        _repolish(self.live_button)
        self.live_button.setText("Start monitoring")
        self.live_log.appendPlainText("Monitoring stopped.")
        self.statusBar().showMessage("Ready.")

    def _stop_live(self, abort: bool = False) -> None:
        """Stop monitoring. Normally the worker is left running until it
        has finished the clips already cut (the ``stopped`` signal then
        resets the button). On window close (``abort``) unfinished clips
        are saved raw and the thread is waited for, never destroyed
        while still running."""
        worker = self._live_worker
        if worker is None:
            return
        worker.stop(abort_processing=abort)
        if abort:
            if not worker.wait(15000):
                worker.terminate()
                worker.wait(2000)
            self._live_worker = None
        else:
            self.live_button.setEnabled(False)
            self.live_button.setText("Finishing clips ...")

    # ------------------------------------------------------------ misc

    def _on_browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder",
                                                  self.out_edit.text())
        if folder:
            self.out_edit.setText(folder)
            self._save_settings()
