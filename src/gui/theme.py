"""Liquid Glass theme for the Cut2Clip GUI.

One Qt style sheet, applied to the whole QApplication in
``src.gui_main`` so windows, dialogs and popups all match.
The main window paints the artwork (``src/gui/background.jpg``)
as its background — see ``MainWindow.paintEvent`` — and every
big panel is Liquid Glass over it: the artwork behind the panel
is blurred, a light white tint sits on top, a bright rim catches
the light at the top edge, and a soft shadow lifts the panel
off the background. The blur and the rim are what make the
glass readable — the text floats on a soft, muted version of
the artwork instead of the sharp streaks. Buttons come in four
looks: primary (black button, white text), accent (muted
green), danger (muted red) and secondary (quiet outline) —
every button in the window uses one of them, so the whole app
feels like one calm, professional design. Input boxes are
70% transparent white with black text.
"""

import sys
from pathlib import Path

from PySide6.QtGui import QPixmap

STYLE = """
QMainWindow, QWidget {
    background: transparent;
    color: #111111;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel { color: #111111; }
QLabel#muted { color: #333333; }
QLabel#option { font-weight: bold; }
QLineEdit#option { font-weight: bold; }
QComboBox { font-weight: bold; }
QLabel#hero {
    background: transparent;
    border: none;
    padding: 4px 0px 0px 0px;
}
QLabel#tagline {
    background: transparent;
    border: none;
    color: #9eecf4;
    font-size: 11px;
    font-weight: bold;
    margin-top: -4px;
    padding: 0px 0px 2px 2px;
}
QWidget#panel {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 10px;
}
QLabel#chip {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 6px;
    padding: 4px 10px;
}
QLabel#info {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 10px;
    padding: 10px 12px;
    color: #222222;
    font-weight: 600;
}
QPushButton {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(0, 0, 0, 0.30);
    border-radius: 8px;
    padding: 10px 20px;
    min-height: 18px;
    color: #111111;
    font-weight: 600;
}
QPushButton:hover { background: #ffffff; border-color: #111111; }
QPushButton:pressed { background: #e5e5e5; }
QPushButton:disabled {
    color: #999999;
    background: rgba(255, 255, 255, 0.30);
    border-color: rgba(0, 0, 0, 0.15);
}
QPushButton#primary {
    background: #111111;
    border: 1px solid #111111;
    color: white;
}
QPushButton#primary:hover {
    background: #000000;
    border-color: #000000;
}
QPushButton#primary:pressed {
    background: #333333;
    border-color: #333333;
}
QPushButton#accent {
    background: #2e8b57;
    border: 1px solid #2e8b57;
    color: white;
}
QPushButton#accent:hover {
    background: #359a63;
    border-color: #359a63;
}
QPushButton#accent:pressed {
    background: #277a4b;
    border-color: #277a4b;
}
QPushButton#danger {
    background: #c04545;
    border: 1px solid #c04545;
    color: white;
}
QPushButton#danger:hover {
    background: #cf5252;
    border-color: #cf5252;
}
QPushButton#danger:pressed {
    background: #a83a3a;
    border-color: #a83a3a;
}
QPushButton#secondary {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(0, 0, 0, 0.35);
    color: #333333;
}
QPushButton#secondary:hover {
    background: #ffffff;
    border-color: #111111;
    color: #111111;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(0, 0, 0, 0.35);
    border-radius: 8px;
    padding: 9px 12px;
    color: #111111;
    selection-background-color: #4a7fb5;
    selection-color: white;
}
QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #111111;
    background: #ffffff;
}
QComboBox::drop-down {
    background: rgba(240, 240, 240, 0.30);
    border: none;
    border-left: 1px solid #d0d0d0;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    width: 28px;
}
QComboBox::down-arrow {
    image: url({arrow});
    width: 16px;
    height: 16px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    background: rgba(240, 240, 240, 0.55);
    border: none;
    border-left: 1px solid #d0d0d0;
    width: 24px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url({up});
    width: 12px;
    height: 12px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url({arrow});
    width: 12px;
    height: 12px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #111111;
    selection-background-color: #4a7fb5;
    selection-color: white;
    border: 1px solid #9a9a9a;
}
QTabWidget::pane {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 10px;
}
QTabBar::tab {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(255, 255, 255, 0.5);
    color: #222222;
    padding: 10px 22px;
    border-radius: 8px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:hover { color: #111111; }
QTabBar::tab:selected {
    background: #111111;
    border: 1px solid #111111;
    color: white;
}
QListWidget {
    background: transparent;
    border: none;
    padding: 6px;
}
QListWidget#glass {
    background: transparent;
    border: 1px solid rgba(255, 255, 255, 0.7);
    border-radius: 10px;
    padding: 6px;
}
QListWidget::item { padding: 8px 10px; border-radius: 6px; }
QListWidget::item:selected { background: rgba(0, 0, 0, 0.08); color: #111111; }
QListWidget::item:hover { background: rgba(0, 0, 0, 0.04); }
QListWidget::indicator {
    width: 16px;
    height: 16px;
    background: #ffffff;
    border: 1px solid #9a9a9a;
    border-radius: 4px;
}
QListWidget::indicator:checked {
    background: #111111;
    border: 1px solid #111111;
    image: url({check});
}
QPlainTextEdit {
    background: transparent;
    border: none;
    color: #222222;
    font-family: "Consolas", "Courier New", monospace;
    padding: 8px;
}
QProgressBar {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(0, 0, 0, 0.12);
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: white;
    font-weight: 600;
}
QProgressBar::chunk {
    background: #4a7fb5;
    border-radius: 7px;
}
QStatusBar { background: transparent; color: #333333; font-weight: 600; }
QStatusBar::item { border: none; }
QMessageBox { background: #ffffff; }
QToolTip {
    background: #ffffff;
    color: #111111;
    border: 1px solid #9a9a9a;
    border-radius: 6px;
    padding: 6px 8px;
}
"""


def _asset_path(name: str) -> str:
    """Absolute path of a bundled GUI asset, or "" if missing.

    Dev runs find it next to this file; a one-file PyInstaller
    bundle finds it under sys._MEIPASS (see cut2clip.spec datas).
    """
    here = Path(__file__).resolve().parent
    candidates = [here / name]
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "src" / "gui" / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.as_posix()
    return ""


def _arrow_path() -> str:
    return _asset_path("down-arrow.png")


def _up_path() -> str:
    return _asset_path("up-arrow.png")


def _check_path() -> str:
    return _asset_path("check.png")


def background_pixmap() -> QPixmap:
    """The main-window background artwork, or a null pixmap if missing."""
    path = _asset_path("background.jpg")
    return QPixmap(path) if path else QPixmap()


def logo_pixmap() -> QPixmap:
    """The header logo (rounded corners baked in), or null if missing."""
    path = _asset_path("logo.png")
    return QPixmap(path) if path else QPixmap()


def background_blurred_pixmap(radius: int = 14) -> QPixmap:
    """A Gaussian-blurred copy of the background artwork.

    This is the Liquid Glass backdrop: the main window draws the
    blurred artwork behind each glass panel so the streaks turn
    into a soft wash the text can sit on. Falls back to the sharp
    artwork when PIL is unavailable.
    """
    path = _asset_path("background.jpg")
    if not path:
        return QPixmap()
    try:
        import io

        from PIL import Image, ImageFilter

        image = Image.open(path).convert("RGB")
        image = image.filter(ImageFilter.GaussianBlur(radius))
        buf = io.BytesIO()
        image.save(buf, "PNG")
        pix = QPixmap()
        pix.loadFromData(buf.getvalue())
        return pix
    except Exception:
        return QPixmap(path)


def apply_theme(app) -> None:
    """Apply the Cut2Clip theme to a QApplication."""
    sheet = STYLE.replace("{arrow}", _arrow_path())
    sheet = sheet.replace("{up}", _up_path())
    sheet = sheet.replace("{check}", _check_path())
    app.setStyleSheet(sheet)
