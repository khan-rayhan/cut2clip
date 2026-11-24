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


def test_theme_stylesheet_is_classic():
    """The Liquid Glass theme uses solid colors only — no gradients —
    with a transparent window (the artwork paints behind it) and
    glass panels on top: transparent in the style sheet, the blur
    and tint painted by the main window, a bright white rim."""
    app = _app()
    apply_theme(app)
    sheet = app.styleSheet()
    assert "qlineargradient" not in sheet
    assert "background: transparent" in sheet
    # Glass panels carry a bright rim, not a solid fill.
    assert "rgba(255, 255, 255, 0.7)" in sheet
    assert "QPushButton#primary" in sheet
    assert "QPushButton#accent" in sheet and "QPushButton#danger" in sheet
    assert "QPushButton#secondary" in sheet
    # Input boxes are 70% transparent white with black text, including
    # the spinbox up/down buttons and the combo drop-down arrow area.
    assert "background: rgba(255, 255, 255, 0.30)" in sheet
    assert "color: #111111" in sheet
    assert "QSpinBox::up-button" in sheet
    assert "QComboBox::drop-down" in sheet
    # Every combo shows a visible down chevron, not just a white box.
    assert "QComboBox::down-arrow" in sheet
    assert "down-arrow.png" in sheet
    # The bottom option labels and values are bold, same font and size.
    assert "QLabel#option" in sheet
    assert "font-weight: bold" in sheet
    # Floating labels sit on glass chips, and the settings rows live
    # in a glass panel, so no text floats on the artwork itself.
    assert "QLabel#chip" in sheet
    assert "QWidget#panel" in sheet
    # Checkboxes are white boxes with a dark check, even on the artwork.
    assert "QListWidget::indicator" in sheet
    assert "check.png" in sheet
    # The spinbox shows visible up/down arrows in their own box
    # next to the number, like the combo chevron.
    assert "QSpinBox::up-arrow" in sheet
    assert "QSpinBox::down-arrow" in sheet
    assert "up-arrow.png" in sheet
    # The hero is the logo image: transparent, borderless, no text styling.
    assert "QLabel#hero" in sheet
    assert "font-size: 36px" not in sheet
    assert "color: #b5e7a0" not in sheet
    # The tagline below the logo is real text at 11px, pulled up
    # tight under the logo with a negative top margin.
    assert "QLabel#tagline" in sheet
    assert "font-size: 11px" in sheet
    assert "margin-top: -4px" in sheet


def test_down_arrow_asset_exists():
    from pathlib import Path

    assert (Path(__file__).resolve().parent.parent
            / "src" / "gui" / "down-arrow.png").is_file()


def test_up_arrow_asset_exists():
    from pathlib import Path

    assert (Path(__file__).resolve().parent.parent
            / "src" / "gui" / "up-arrow.png").is_file()


def test_logo_asset_exists():
    from pathlib import Path

    from PIL import Image

    logo = (Path(__file__).resolve().parent.parent
            / "src" / "gui" / "logo.png")
    assert logo.is_file()
    image = Image.open(logo).convert("RGBA")
    # Rounded corners: the four corner pixels are transparent.
    assert image.getpixel((0, 0))[3] == 0
    assert image.getpixel((image.width - 1, 0))[3] == 0
    assert image.getpixel((0, image.height - 1))[3] == 0
    assert image.getpixel((image.width - 1, image.height - 1))[3] == 0
    # Blended with the background: the alpha channel spans fully
    # transparent (dark background) to fully opaque (bright letters).
    assert image.getchannel("A").getextrema() == (0, 255)
    # Sharp edges: few semi-transparent pixels (only the 1px edge).
    import numpy as np

    alpha = np.asarray(image.getchannel("A"))
    mid = ((alpha > 10) & (alpha < 245)).mean()
    assert mid < 0.10
    # No colour filled in the letters' empty spaces (the "p" bowl and
    # the tagline A/R/D counters): only the thin letter-outline rims
    # may still match the navy background, never a filled blob.
    arr = np.asarray(image).astype(np.float32)
    navy = np.array([13.0, 22.0, 35.0])
    dist = np.sqrt(((arr[..., :3] - navy) ** 2).sum(axis=2))
    assert int(((arr[..., 3] > 128) & (dist < 40)).sum()) < 2500


def test_check_asset_exists():
    from pathlib import Path

    assert (Path(__file__).resolve().parent.parent
            / "src" / "gui" / "check.png").is_file()


def test_background_asset_exists():
    from pathlib import Path

    assert (Path(__file__).resolve().parent.parent
            / "src" / "gui" / "background.jpg").is_file()


def test_background_blurred_pixmap_loads():
    from src.gui.theme import background_blurred_pixmap

    _app()  # QPixmap needs a QApplication
    pix = background_blurred_pixmap()
    assert not pix.isNull()
    assert pix.width() > 0 and pix.height() > 0


def test_background_pixmap_loads():
    from src.gui.theme import background_pixmap

    _app()  # QPixmap needs a QApplication
    pix = background_pixmap()
    assert not pix.isNull()
    assert pix.width() > 0 and pix.height() > 0


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
    assert window.tagline_label.objectName() == "tagline"
    assert window.tagline_label.text() == (
        "C R E A T E .  E D I T .  S H A R E .")
    # The hero is the logo image, not a glass panel: plain on the artwork.
    assert all(w is not window.hero_label for w, _ in window._glass)
    # The header shows the logo (rounded corners baked in), 45px tall.
    from PySide6.QtWidgets import QLabel

    assert isinstance(window.hero_label, QLabel)
    assert window.hero_label.text() == ""
    pixmap = window.hero_label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.height() == 45
    # A realistic Pre-Recorded state renders without crashing.
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
