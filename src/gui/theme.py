"""Colorful, modern dark theme for the Cut2Clip GUI.

One Qt style sheet, applied to the whole QApplication in
``src.gui_main`` so windows, dialogs and popups all match.
Palette: deep navy background, violet -> pink -> orange gradients
for the main actions, green for "go" and red for "stop".
"""

STYLE = """
QMainWindow, QWidget {
    background: #12142a;
    color: #f2f3ff;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QLabel { color: #f2f3ff; }
QLabel#hero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c5cff, stop:0.5 #ff5c8a, stop:1 #ff9a3d);
    color: white;
    font-size: 17px;
    font-weight: bold;
    border-radius: 12px;
    padding: 12px 16px;
}
QLabel#info {
    background: #1d2040;
    border: 1px solid #353a63;
    border-radius: 8px;
    padding: 8px 10px;
    color: #c9cdf2;
}
QPushButton {
    background: #262a4d;
    border: 1px solid #3d4272;
    border-radius: 9px;
    padding: 8px 18px;
    color: #f2f3ff;
    font-weight: 600;
}
QPushButton:hover { background: #2f345c; border-color: #7c5cff; }
QPushButton:pressed { background: #1d2040; }
QPushButton:disabled {
    color: #6b7099;
    background: #1d2040;
    border-color: #2a2e4d;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c5cff, stop:1 #ff5c8a);
    border: none;
    color: white;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8d6fff, stop:1 #ff6f9b);
}
QPushButton#accent {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00b578, stop:1 #2fd48a);
    border: none;
    color: white;
}
QPushButton#danger {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ff5c5c, stop:1 #ff7a3d);
    border: none;
    color: white;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #1d2040;
    border: 1px solid #353a63;
    border-radius: 8px;
    padding: 7px 10px;
    color: #f2f3ff;
    selection-background-color: #7c5cff;
}
QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #7c5cff;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #1d2040;
    selection-background-color: #7c5cff;
    border: 1px solid #353a63;
}
QTabWidget::pane {
    background: #181b33;
    border: 1px solid #2e3358;
    border-radius: 10px;
}
QTabBar::tab {
    background: #23264a;
    color: #a2a8d0;
    padding: 9px 20px;
    border-radius: 8px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c5cff, stop:1 #ff5c8a);
    color: white;
}
QListWidget {
    background: #181b33;
    border: 1px solid #2e3358;
    border-radius: 10px;
    padding: 4px;
}
QListWidget::item { padding: 7px 8px; border-radius: 6px; }
QListWidget::item:selected { background: #7c5cff; color: white; }
QListWidget::item:hover { background: #262a4d; }
QPlainTextEdit {
    background: #0e1024;
    border: 1px solid #2e3358;
    border-radius: 10px;
    color: #c9f5d8;
    font-family: "Consolas", "Courier New", monospace;
    padding: 6px;
}
QProgressBar {
    background: #23264a;
    border: none;
    border-radius: 7px;
    height: 14px;
    text-align: center;
    color: white;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c5cff, stop:1 #ff5c8a);
    border-radius: 7px;
}
QStatusBar { color: #a2a8d0; }
QStatusBar::item { border: none; }
QMessageBox { background: #1d2040; }
"""


def apply_theme(app) -> None:
    """Apply the Cut2Clip theme to a QApplication."""
    app.setStyleSheet(STYLE)
