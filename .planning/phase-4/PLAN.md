# Phase 4 — PySide6 GUI and PyInstaller packaging

## Goal
A real desktop app: paste a URL, see whether it is a VOD or a
live stream, get 40-second vertical clips with captions, watch
progress live, and open the finished files. Then package it as a
single-file executable the user can run on Windows without
installing Python.

## Verified facts (research done 2026-11-18)
- PySide6 is the locked UI framework (Phase 0 decision). Qt
  Widgets, not QML: simpler, and every control needed here
  (lists, progress bars, log view) is a stock widget.
- Long work (probing, clipping, transcribing, live monitoring)
  must run in QThreads. The GUI thread never blocks; workers
  report progress through signals.
- PyInstaller bundles the Python code plus the heavy native
  libraries (Qt, OpenCV, onnxruntime, MediaPipe, ctranslate2).
  ffmpeg and ffprobe are system binaries, so the bundle ships
  them as binaries and the app puts the bundle folder first on
  PATH at startup, so every subprocess call finds them.
- The packaged app on the user PC is Windows. This VM builds
  and smoke-tests the Linux bundle; the Windows build uses the
  same spec file and the build script in `packaging/`.
- MediaPipe's Tasks library needs libEGL/libGLES on Linux. The
  packaged Linux bundle includes those libraries as binaries.
  On Windows the mediapipe wheel works without them.

## Tasks

### 4.1 GUI shell (`src/gui/main_window.py`)
- One window: URL bar with a Detect button, a status line showing
  title, duration, live/VOD and heatmap presence, and two mode
  panels (VOD clips list, live monitor log).
- VOD panel: ranked 40-second windows from Phase 1 with a
  checkbox per window, a Process Selected button, and a progress
  bar per job. Finished clips appear in the output list with
  their duration; double-click opens the file.
- Live panel: Start/Stop monitoring, the Z threshold, a live log
  of spikes, and saved clips as they appear.
- Settings: output folder, whisper model (tiny/base/small),
  Z threshold, device (auto/CPU/CUDA). Persisted with QSettings.
- Check: the window constructs offscreen with all controls
  present; settings round-trip through QSettings.

### 4.2 Workers (`src/gui/workers.py`)
- `ProbeWorker(QThread)`: probes a URL, emits the VideoInfo or an
  error string. `ClipsWorker`: lists highlight windows.
  `ProcessWorker`: runs the Phase 3 pipeline for one clip and
  emits progress lines. `LiveWorker`: runs the Phase 2 monitor
  and forwards spike and clip events.
- Check: each worker finishes and emits its result when driven
  from a test event loop; a failing probe emits an error, never
  a crash.

### 4.3 Entry point (`src/gui_main.py`)
- `python -m src.gui_main` starts the app. On startup it puts
  the bundle folder first on PATH so bundled ffmpeg/ffprobe win.
- `--smoke-test` builds the main window offscreen and exits 0.
  This is what the packaging check runs.
- Check: `--smoke-test` exits 0 offscreen.

### 4.4 Packaging (`packaging/`)
- `shorts-app.spec`: one-file build, windowed, with the models
  folder as data, hidden imports for mediapipe, faster-whisper,
  onnxruntime, cv2, yt_dlp, streamlink and chat_downloader, and
  the system ffmpeg/ffprobe plus libEGL/libGLESv2 as binaries.
- `packaging/build-windows.md`: the exact steps on the user PC
  (install Python 3.12, create the venv, install requirements,
  run the build, find the exe in dist/).
- Check: `pyinstaller shorts-app.spec` finishes and
  `dist/shorts-app --smoke-test` exits 0 with
  QT_QPA_PLATFORM=offscreen.

## Waves
- Wave 1: 4.1 and 4.2 (GUI plus workers, offscreen tests).
- Wave 2: 4.3 (entry point, smoke flag).
- Wave 3: 4.4 (packaging, the long pole).

## Verification criteria
- Every check above passes.
- The GUI never freezes while a worker runs (workers live in
  their own threads; the main window stays responsive).
- The packaged bundle starts and its smoke test passes.
- A VOD URL processed end to end through the GUI worker path
  produces a 1080x1920 captioned clip.

## Out of scope for this phase
- The Windows build itself (built on the user PC from
  `packaging/build-windows.md`).
- Uploading, scheduling, or posting (after v1).
- macOS packaging (same spec, built on a Mac).
