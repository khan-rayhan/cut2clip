# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Cut2Clip.

One-file, windowed build. The models folder (BlazeFace, YOLOv8n)
ships as data; ffmpeg/ffprobe and, on Linux, the MediaPipe system
libraries ship as binaries. The app puts the bundle folder first
on PATH at startup so every subprocess call finds them.

Build on Linux:  pyinstaller cut2clip.spec
Build on Windows: same command, from packaging/build-windows.md.
"""

import os
import shutil
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
HERE = Path(SPECPATH)

datas = [(str(HERE / "models"), "models")]

binaries = []
for tool in ("ffmpeg", "ffprobe"):
    path = shutil.which(tool)
    if path:
        binaries.append((path, "."))

if sys.platform.startswith("linux"):
    # MediaPipe's FaceDetector needs libEGL + libGLESv2. The
    # /usr/lib copies vanish on every VM replacement, so also
    # search the durable copies under ~/mediapipe-libs (the same
    # ones dev runs use via LD_LIBRARY_PATH). Without these the
    # bundle builds fine but fails at startup with
    # "ImportError: libEGL.so.1".
    home = Path.home()
    for lib in ("libEGL.so.1", "libGLESv2.so.2"):
        for folder in (
            "/usr/lib/x86_64-linux-gnu",
            "/lib/x86_64-linux-gnu",
            str(home / "mediapipe-libs" / "egl" / "usr" / "lib" / "x86_64-linux-gnu"),
            str(home / "mediapipe-libs" / "gles" / "usr" / "lib" / "x86_64-linux-gnu"),
        ):
            candidate = os.path.join(folder, lib)
            if os.path.exists(candidate):
                binaries.append((candidate, "."))
                break

hiddenimports = [
    "mediapipe",
    "faster_whisper",
    "onnxruntime",
    "cv2",
    "yt_dlp",
    "streamlink",
    "chat_downloader",
    "av",
]

# collect_all is only for packages PyInstaller has no hook for.
# cv2 and onnxruntime DO have hooks (pyinstaller-hooks-contrib):
# collecting them again duplicates their native libraries in the
# archive and corrupts the one-file bundle (the first build failed
# to extract cv2/cv2.abi3.so with a decompression error).
for package in ("mediapipe", "faster_whisper"):
    tmp_ret = collect_all(package)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [str(HERE / "src" / "gui_main.py")],
    pathex=[str(HERE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# The C2C icon (packaging/icon.ico) is embedded in the exe on
# Windows; on other platforms PyInstaller ignores it.
EXE_ICON = str(HERE / "packaging" / "icon.ico") if sys.platform.startswith("win") else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="cut2clip",
    icon=EXE_ICON,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
