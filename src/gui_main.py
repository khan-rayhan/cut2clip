"""Desktop entry point: ``python -m src.gui_main``.

When frozen by PyInstaller the bundle folder holds ffmpeg, ffprobe
and the MediaPipe system libraries, so it goes first on PATH before
anything else runs. ``--smoke-test`` builds the main window
offscreen and exits 0; the packaging check runs exactly that.
"""

from __future__ import annotations

import os
import sys


def _prepend_bundle_dir() -> None:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        os.environ["PATH"] = bundle + os.pathsep + os.environ.get("PATH", "")


def main(argv: list[str] | None = None) -> int:
    _prepend_bundle_dir()
    from PySide6.QtWidgets import QApplication

    # Absolute import on purpose: when PyInstaller freezes this file
    # it runs as a top-level script with no parent package, so a
    # relative import (``from .gui...``) fails with "attempted
    # relative import with no known parent package".
    from src.gui.main_window import MainWindow

    app = QApplication(list(argv or sys.argv))
    window = MainWindow()
    if "--smoke-test" in (argv or sys.argv):
        window.show()
        app.processEvents()
        print("Smoke test OK: main window built.")
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
