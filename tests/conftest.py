"""Test setup: MediaPipe's Tasks native library needs libEGL.so.1
and libGLESv2.so.2, which this VM does not ship. The .debs were
extracted to ~/mediapipe-libs; put them on the loader path before
anything imports mediapipe. On a machine with the libraries
installed system-wide this is a no-op."""

import os
from pathlib import Path

for sub in ("egl/usr/lib/x86_64-linux-gnu", "gles/usr/lib/x86_64-linux-gnu"):
    lib_dir = str(Path.home() / "mediapipe-libs" / sub)
    if os.path.isdir(lib_dir):
        current = os.environ.get("LD_LIBRARY_PATH", "")
        if lib_dir not in current.split(":"):
            os.environ["LD_LIBRARY_PATH"] = lib_dir + (":" + current if current else "")
