"""Main window: paste a URL, detect pre-recorded or live, get clips."""

from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QRect, QRectF, QSettings, Qt, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QDoubleSpinBox, QTabWidget,
    QVBoxLayout, QWidget)

from .. import highlights
from .outlined_label import OutlinedLabel
from .theme import background_blurred_pixmap, background_pixmap
from .workers import ClipsWorker, LiveWorker, ProbeWorker, VodClipWorker

ORG = "ShortsApp"
APP = "ShortsApp"

# Display text for the bottom option dropdowns: the shown word starts
# with a capital letter, while the stored value stays lowercase so the
# pipeline, settings and saved values never change.
_COMBO_OPTIONS = {
    "model": [("Tiny", "tiny"), ("Base", "base"), ("Small", "small")],
    "performance": [("Auto", "auto"), ("Lite", "lite"),
                    ("Balanced", "balanced"), ("Fast", "fast")],
    "captions": [("Hormozi", "hormozi"), ("TikTok", "tiktok"),
                 ("Karaoke", "karaoke"), ("Neon", "neon")],
    "device": [("Auto", "auto"), ("CPU", "cpu"), ("CUDA", "cuda")],
}


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


def _unused_output_path(path: str) -> str:
    """Avoid silently overwriting a clip from an earlier run."""
    if not os.path.exists(path):
        return path
    stem, suffix = os.path.splitext(path)
    index = 2
    while os.path.exists(f"{stem}-{index}{suffix}"):
        index += 1
    return f"{stem}-{index}{suffix}"


class MainWindow(QMainWindow):
    def __init__(self, settings_org: str = ORG, settings_app: str = APP):
        super().__init__()
        from .. import __version__
        self.setWindowTitle(f"Cut2Clip v{__version__} — 40-second vertical clips")
        self.resize(760, 560)
        self.settings = QSettings(settings_org, settings_app)
        self._workers: list = []
        self._windows: list[highlights.ClipWindow] = []
        # Main-window background artwork, cover-scaled and cached per size.
        self._bg_pixmap = background_pixmap()
        self._bg_blurred = background_blurred_pixmap()
        self._bg_scaled = None
        self._bg_blurred_scaled = None
        self._live_worker: LiveWorker | None = None
        self._build_ui()
        self._load_settings()
        # Liquid Glass panels: (widget, corner radius). The paintEvent
        # draws the blurred artwork behind each one, plus a soft shadow
        # and a bright top edge. Only the visible tab page is painted.
        self._glass = [
            (self.info_label, 10),
            (self.vod_tab, 10),
            (self.live_tab, 10),
            (self.outputs_list, 10),
            (self.settings_panel, 10),
            (self.finished_label, 6),
            (self.statusBar(), 0),
        ]

    # ------------------------------------------------------------ UI

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._bg_scaled = None  # rebuilt on the next paint
        self._bg_blurred_scaled = None
        super().resizeEvent(event)

    @staticmethod
    def _cover_scaled(pixmap, size):
        """Scale a pixmap to cover a size, centre-cropped."""
        scaled = pixmap.scaled(
            size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = (scaled.width() - size.width()) // 2
        y = (scaled.height() - size.height()) // 2
        return scaled.copy(x, y, size.width(), size.height())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if not self._bg_pixmap.isNull():
            if self._bg_scaled is None:
                self._bg_scaled = self._cover_scaled(
                    self._bg_pixmap, self.size())
                if not self._bg_blurred.isNull():
                    self._bg_blurred_scaled = self._cover_scaled(
                        self._bg_blurred, self.size())
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self._bg_scaled)
            for widget, radius in self._glass:
                if not widget.isVisible():
                    continue
                rect = QRect(
                    widget.mapTo(self, QPoint(0, 0)), widget.size())
                if rect.isEmpty():
                    continue
                path = QPainterPath()
                path.addRoundedRect(QRectF(rect), radius, radius)
                # Soft shadow: a few expanding rounded rects, fading out.
                for grow, alpha in ((6, 8), (4, 12), (2, 18)):
                    shadow = QPainterPath()
                    shadow.addRoundedRect(
                        QRectF(rect.adjusted(-grow, -grow, grow, grow + 2)),
                        radius + grow, radius + grow)
                    painter.fillPath(shadow, QColor(0, 0, 0, alpha))
                # Blurred backdrop + a light glass tint.
                painter.save()
                painter.setClipPath(path)
                if self._bg_blurred_scaled is not None:
                    painter.drawPixmap(
                        rect, self._bg_blurred_scaled, rect)
                painter.fillRect(rect, QColor(255, 255, 255, 50))
                # Specular top edge: the light catching the glass rim.
                painter.setPen(QPen(QColor(255, 255, 255, 140), 1))
                painter.drawLine(
                    rect.left() + radius, rect.top() + 1,
                    rect.right() - radius, rect.top() + 1)
                painter.restore()
        super().paintEvent(event)

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 12, 14, 12)

        self.hero_label = OutlinedLabel(
            "Cut2Clip", outline_color="#1a1a1a", fill_alpha=150)
        self.hero_label.setObjectName("hero")
        layout.addWidget(self.hero_label)

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

        self.vod_tab = QWidget()
        vod_layout = QVBoxLayout(self.vod_tab)
        vod_layout.setSpacing(10)
        self.windows_list = QListWidget()
        vod_layout.addWidget(self.windows_list)
        vod_buttons = QHBoxLayout()
        vod_buttons.setSpacing(8)
        self.process_button = QPushButton("Process Selected")
        self.process_button.setObjectName("primary")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self._on_process_selected)
        vod_buttons.addWidget(self.process_button)
        self.auto_button = QPushButton("Auto-Clip Top 3")
        self.auto_button.setObjectName("primary")
        self.auto_button.setEnabled(False)
        self.auto_button.setToolTip(
            "Process the top 3 highlight windows automatically, "
            "no ticking needed.")
        self.auto_button.clicked.connect(self._on_auto_top3)
        vod_buttons.addWidget(self.auto_button)
        vod_layout.addLayout(vod_buttons)
        self.vod_progress = QProgressBar()
        self.vod_progress.setVisible(False)
        self.vod_progress.setMaximum(100)
        self.vod_progress.setFormat("%p%")
        vod_layout.addWidget(self.vod_progress)
        self.tabs.addTab(self.vod_tab, "Pre-Recorded Clips")

        self.live_tab = QWidget()
        live_layout = QVBoxLayout(self.live_tab)
        live_layout.setSpacing(10)
        live_controls = QHBoxLayout()
        live_controls.setSpacing(8)
        live_controls.addWidget(QLabel("Spike threshold:"))
        self.z_spin = QDoubleSpinBox()
        self.z_spin.setRange(1.0, 5.0)
        self.z_spin.setSingleStep(0.5)
        self.z_spin.setValue(2.5)
        self.z_spin.setToolTip(
            "How big a chat burst must be to cut a clip. "
            "Lower catches smaller moments; higher catches "
            "only the biggest ones. "
            "Low is below 2.0, Medium 2.0–3.0, High above 3.0.")
        self.z_level_label = QLabel()
        self.z_level_label.setObjectName("muted")
        self.z_level_label.setText(self._z_level_text(self.z_spin.value()))
        self.z_spin.valueChanged.connect(self._on_z_changed)
        live_controls.addWidget(self.z_spin)
        live_controls.addWidget(self.z_level_label)
        self.live_button = QPushButton("Start Monitoring")
        self.live_button.setObjectName("accent")
        self.live_button.setEnabled(False)
        self.live_button.clicked.connect(self._on_live_toggle)
        live_controls.addWidget(self.live_button)
        live_controls.addStretch()
        live_layout.addLayout(live_controls)
        self.live_log = QPlainTextEdit()
        self.live_log.setReadOnly(True)
        live_layout.addWidget(self.live_log)
        self.live_progress = QProgressBar()
        self.live_progress.setVisible(False)
        self.live_progress.setMaximum(100)
        self.live_progress.setFormat("%p%")
        live_layout.addWidget(self.live_progress)
        self.live_clips = QListWidget()
        live_layout.addWidget(self.live_clips)
        self.tabs.addTab(self.live_tab, "Live Monitor")

        layout.addWidget(self.tabs)

        self.outputs_list = QListWidget()
        self.outputs_list.setObjectName("glass")
        self.outputs_list.itemDoubleClicked.connect(self._on_open_output)
        self.finished_label = QLabel("Finished Clips (Double-Click to Open):")
        self.finished_label.setObjectName("chip")
        finished_row = QHBoxLayout()
        finished_row.addWidget(self.finished_label)
        finished_row.addStretch()
        layout.addLayout(finished_row)
        layout.addWidget(self.outputs_list)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        out_label = QLabel("Output folder:")
        out_label.setObjectName("option")
        settings_row.addWidget(out_label)
        self.out_edit = QLineEdit()
        self.out_edit.setObjectName("option")
        settings_row.addWidget(self.out_edit)
        browse = QPushButton("Browse")
        browse.setObjectName("secondary")
        browse.clicked.connect(self._on_browse_out)
        settings_row.addWidget(browse)

        options_row = QHBoxLayout()
        options_row.setSpacing(8)
        model_label = QLabel("Whisper model:")
        model_label.setObjectName("option")
        options_row.addWidget(model_label)
        self.model_combo = QComboBox()
        for text, value in _COMBO_OPTIONS["model"]:
            self.model_combo.addItem(text, value)
        options_row.addWidget(self.model_combo)
        perf_label = QLabel("Performance:")
        perf_label.setObjectName("option")
        options_row.addWidget(perf_label)
        self.performance_combo = QComboBox()
        for text, value in _COMBO_OPTIONS["performance"]:
            self.performance_combo.addItem(text, value)
        self.performance_combo.setToolTip(
            "Auto selects a profile based on available RAM and CPU cores.")
        options_row.addWidget(self.performance_combo)
        caption_label = QLabel("Captions:")
        caption_label.setObjectName("option")
        options_row.addWidget(caption_label)
        self.caption_combo = QComboBox()
        for text, value in _COMBO_OPTIONS["captions"]:
            self.caption_combo.addItem(text, value)
        self.caption_combo.setToolTip(
            "Caption style for every clip: Hormozi, TikTok, Karaoke, Neon.")
        options_row.addWidget(self.caption_combo)
        device_label = QLabel("Device:")
        device_label.setObjectName("option")
        options_row.addWidget(device_label)
        self.device_combo = QComboBox()
        for text, value in _COMBO_OPTIONS["device"]:
            self.device_combo.addItem(text, value)
        options_row.addWidget(self.device_combo)
        options_row.addStretch()
        self.settings_panel = QWidget()
        self.settings_panel.setObjectName("panel")
        panel_layout = QVBoxLayout(self.settings_panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.addLayout(settings_row)
        panel_layout.addLayout(options_row)
        layout.addWidget(self.settings_panel)

        self.statusBar().showMessage("Ready.")
        self.setCentralWidget(central)

    # ------------------------------------------------------------ settings

    @staticmethod
    def _set_combo(combo, value) -> None:
        """Select a combo item by its stored value, ignoring display text."""
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _load_settings(self) -> None:
        self.out_edit.setText(self.settings.value(
            "output_folder", os.path.join(os.path.expanduser("~"), "ShortsClips")))
        self._set_combo(self.model_combo, self.settings.value("model", "tiny"))
        self._set_combo(self.caption_combo,
                        self.settings.value("caption_style", "hormozi"))
        self._set_combo(self.device_combo, self.settings.value("device", "auto"))
        self._set_combo(self.performance_combo,
                        self.settings.value("performance_mode", "auto"))
        self.z_spin.setValue(float(self.settings.value("z_threshold", 2.5)))

    def _save_settings(self) -> None:
        self.settings.setValue("output_folder", self.out_edit.text())
        self.settings.setValue("model", self.model_combo.currentData())
        self.settings.setValue("caption_style",
                               self.caption_combo.currentData())
        self.settings.setValue("device", self.device_combo.currentData())
        self.settings.setValue("performance_mode", self.performance_combo.currentData())
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
        kind = "LIVE" if info.is_live else "Pre-Recorded"
        heat = f", heatmap {len(info.heatmap)} points" if info.has_heatmap else ", no heatmap"
        dur = _fmt(info.duration) if info.duration else "live"
        self.info_label.setText(f"{info.title or '(no title)'} — {kind}, {dur}{heat}")
        if info.is_live:
            self.live_button.setEnabled(True)
            self.tabs.setCurrentIndex(1)
            self.statusBar().showMessage("Live stream detected. Start Monitoring when ready.")
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
        self.auto_button.setEnabled(bool(windows))
        self.statusBar().showMessage(f"{len(windows)} highlight windows found.")

    # ------------------------------------------------------------ Pre-Recorded process

    def _on_process_selected(self) -> None:
        selected = [self._windows[i] for i in range(self.windows_list.count())
                    if self.windows_list.item(i).checkState() == Qt.CheckState.Checked]
        if not selected:
            QMessageBox.warning(self, "Nothing Selected", "Tick at least one window.")
            return
        self._start_processing(selected)

    def _on_auto_top3(self) -> None:
        """One-click Pre-Recorded auto-clip: process the top 3 highlight
        windows, no ticking needed. Fewer than 3 windows just means
        fewer clips."""
        if not self._windows:
            QMessageBox.warning(self, "No Windows",
                                "Detect a pre-recorded video first to find highlight windows.")
            return
        self._start_processing(list(self._windows[:3]))

    def _start_processing(self, windows: list) -> None:
        out_dir = self.out_edit.text().strip()
        os.makedirs(out_dir, exist_ok=True)
        self.process_button.setEnabled(False)
        self.auto_button.setEnabled(False)
        self.vod_progress.setVisible(True)
        self.vod_progress.setValue(0)
        self._pending = list(windows)
        self._total_clips = len(windows)
        self._done_clips = 0
        self._failed_clips = 0
        self._process_next()

    def _process_next(self) -> None:
        if not self._pending:
            self.process_button.setEnabled(True)
            self.auto_button.setEnabled(True)
            self.vod_progress.setVisible(False)
            summary = f"Finished: {self._done_clips - self._failed_clips} saved, {self._failed_clips} failed."
            self.statusBar().showMessage(summary)
            return
        window = self._pending.pop(0)
        stamp = _fmt(window.start).replace(":", "-")
        out_path = _unused_output_path(os.path.join(
            self.out_edit.text().strip(), f"clip-{stamp}.mp4"))
        self.vod_progress.setValue(0)
        worker = VodClipWorker(self._current_url, window.start, window.end,
                               out_path, model=self.model_combo.currentData(),
                               caption_style=self.caption_combo.currentData(),
                               device=self.device_combo.currentData(),
                               performance_mode=self.performance_combo.currentData())
        worker.progress.connect(self.statusBar().showMessage)
        worker.progress_pct.connect(self._on_clip_progress)
        worker.finished_file.connect(self._on_clip_done)
        worker.failed.connect(self._on_clip_failed)
        worker.finished.connect(lambda: self._workers.remove(worker))
        self._workers.append(worker)
        worker.start()

    def _on_clip_progress(self, pct: int, label: str) -> None:
        """Per-clip progress: the bar shows the current clip's % and the
        status bar names the clip and the stage."""
        self.vod_progress.setValue(max(0, min(100, pct)))
        self.statusBar().showMessage(
            f"Clip {self._done_clips + 1} of {self._total_clips} — "
            f"{max(0, min(100, pct))}% {label}")

    def _on_clip_done(self, path: str) -> None:
        self.outputs_list.addItem(path)
        self._done_clips += 1
        self._process_next()

    def _on_clip_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Clip Failed", message)
        self._done_clips += 1
        self._process_next()

    def _on_open_output(self, item: QListWidgetItem) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(item.text()))

    # ------------------------------------------------------------ live

    @staticmethod
    def _z_level_text(value: float) -> str:
        """Plain-language level for a spike threshold value."""
        if value < 2.0:
            return "Low"
        if value <= 3.0:
            return "Medium"
        return "High"

    def _on_z_changed(self, value: float) -> None:
        self.z_level_label.setText(self._z_level_text(value))

    def _on_live_toggle(self) -> None:
        if self._live_worker is not None:
            self._stop_live()
            return
        out_dir = self.out_edit.text().strip()
        os.makedirs(out_dir, exist_ok=True)
        self._live_worker = LiveWorker(self._current_url, out_dir,
                                       z_threshold=self.z_spin.value(),
                                       model=self.model_combo.currentData(),
                                       caption_style=self.caption_combo.currentData(),
                                       performance_mode=self.performance_combo.currentData(),
                                       device=self.device_combo.currentData())
        self._live_worker.event.connect(self._on_live_event)
        self._live_worker.failed.connect(self._on_live_failed)
        self._live_worker.stopped.connect(self._on_live_stopped)
        self._live_worker.start()
        self.live_button.setObjectName("danger")
        _repolish(self.live_button)
        self.live_button.setText("Stop Monitoring")
        self.live_log.appendPlainText("Monitoring started.")
        self.statusBar().showMessage("Monitoring live chat ...")

    def _on_live_event(self, event: dict) -> None:
        if event["type"] == "spike":
            self.live_log.appendPlainText(
                f"SPIKE {event['time']}  z={event['z']:.1f}  "
                f"{event['count']} msgs/10s")
        elif event["type"] == "status":
            self.live_log.appendPlainText(event["text"])
        elif event["type"] == "progress":
            pct = max(0, min(100, int(event["pct"])))
            self.live_progress.setVisible(True)
            self.live_progress.setValue(pct)
            self.statusBar().showMessage(
                f"Processing live clip — {pct}% {event['label']}")
        elif event["type"] == "clip":
            self.live_clips.addItem(event["path"])
            self.outputs_list.addItem(event["path"])
            self.live_progress.setVisible(False)
            self.live_progress.setValue(0)
            self.live_log.appendPlainText(f"Saved {event['path']}")

    def _on_live_failed(self, message: str) -> None:
        self.live_log.appendPlainText(f"Monitor failed: {message}")

    def _on_live_stopped(self) -> None:
        self._live_worker = None
        self.live_button.setEnabled(True)
        self.live_button.setObjectName("accent")
        _repolish(self.live_button)
        self.live_button.setText("Start Monitoring")
        self.live_log.appendPlainText("Monitoring stopped.")
        self.statusBar().showMessage("Ready.")

    def _stop_live(self, abort: bool = False) -> None:
        """Stop Monitoring. Normally the worker is left running until it
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
            self.live_button.setText("Finishing Clips ...")

    # ------------------------------------------------------------ misc

    def _on_browse_out(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder",
                                                  self.out_edit.text())
        if folder:
            self.out_edit.setText(folder)
            self._save_settings()
