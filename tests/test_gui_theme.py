"""The colorful theme applies and the main window renders with it.

Runs offscreen, so it works on CI runners with no display too.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.theme import STYLE, apply_theme  # noqa: E402


def _app():
    app = QApplication.instance()
    return app or QApplication([])


def test_theme_stylesheet_has_brand_gradients():
    app = _app()
    apply_theme(app)
    sheet = app.styleSheet()
    assert "7c5cff" in sheet and "ff5c8a" in sheet and "ff9a3d" in sheet
    assert "QPushButton#primary" in sheet


def test_main_window_builds_with_theme(tmp_path):
    from src.gui.main_window import MainWindow
    from src.highlights import ClipWindow

    app = _app()
    apply_theme(app)
    window = MainWindow(settings_org="ShortsAppTest", settings_app="ThemeTest")
    window.show()
    app.processEvents()
    assert window.detect_button.objectName() == "primary"
    assert window.process_button.objectName() == "primary"
    assert window.live_button.objectName() == "accent"
    assert window.info_label.objectName() == "info"
    # A realistic VOD state renders without crashing.
    window._on_windows([
        ClipWindow(start=12.0, end=52.0, peak_time=30.0, score=0.91,
                   source="heatmap"),
        ClipWindow(start=120.0, end=160.0, peak_time=140.0, score=0.74,
                   source="audio"),
    ])
    app.processEvents()
    shot = tmp_path / "window.png"
    assert window.grab().save(str(shot)) and shot.stat().st_size > 0
    window.close()
