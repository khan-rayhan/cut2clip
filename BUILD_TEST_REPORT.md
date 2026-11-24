# Cut2Clip v1.0.3 Test and Review Report

> Note: this code was reviewed as v1.0.5 (built on an intermediate
> v1.0.4) and is released as v1.0.3 — only the version number
> changed, the code is the same. An independent re-run of the suite
> on 2026-11-24 gave 99 passed, 0 failed, 7 deselected, plus a real
> 15s end-to-end render (Rick Astley 18–33s, tiny, Hormozi):
> 1080x1920 H.264 + AAC, exactly 15.000s, 25 words, captions burned
> in, 25.0s total.

Date: 2026-11-24
Base: Cut2Clip v1.0.4 source archive
Environment: Linux x86_64, Python 3.12.3, FFmpeg 6.1.1, yt-dlp 2026.11.23, mediapipe 1.2.3 (as pinned), PySide6 6.12, faster-whisper 1.2.1, streamlink 8.6.3

## Result

| Run | Result |
|---|---:|
| v1.0.4 offline suite incl. full PySide6 GUI tests, before any change | 82 passed |
| v1.0.3 full suite incl. real-time live monitor and ring-buffer recording tests | 101 passed, 5 deselected |
| New regression tests (`tests/test_regressions_v105.py`) run against the OLD code | 16 of 17 fail (the 17th checks yt-dlp's own behaviour) |

The 5 deselected tests need YouTube access or a Whisper model download.

## What the review found

All fixes are listed in CHANGELOG.md under v1.0.3. The most serious: pre-recorded clips were 0 bytes because the GUI pre-created the temp file and yt-dlp skipped the download as "already downloaded" (reproduced against a local HTTP server).

## Still NOT verified (needs your PC / network)

- Real YouTube metadata probe and section download (the sandbox cannot reach YouTube). The format selector in `ingestion.download_section` has no final catch-all fallback; a video with neither H.264 nor m4a at 1080p or below would fail with "Requested format is not available".
- Real Whisper transcription (model download blocked here).
- Real live-stream resolution and chat (Twitch / YouTube / Facebook).
- PyInstaller build, packaged exe smoke test, Inno Setup installer, NVIDIA/CUDA behaviour (Windows only).

## Known limitation (not changed)

- Live mode cuts each raw clip with plain `libx264` at the default preset before the pipeline re-encodes it; on a slow CPU that cut can take a while. Using the performance profile for the raw cut would speed it up.

# Cut2Clip v1.0.4 Build and Test Report

Date: 2026-11-24  
Base: user-uploaded Cut2Clip v1.0.3 source archive  
Target: Windows 10/11, Python 3.12

## Pre-recorded YouTube workflow review

The v1.0.3 source already contained a complete pre-recorded-video workflow:

1. `src/ingestion.py` probes YouTube metadata, distinguishes live from pre-recorded videos, reads Most Replayed heatmap data, extracts automatic caption-track URLs, fetches a bounded number of comments, resolves a direct audio stream, and downloads a selected time range.
2. `src/highlights.py` ranks 40-second windows using the Most Replayed heatmap and timestamped comment density. When heatmap windows are unavailable, it falls back to streamed audio-energy analysis and available YouTube transcript events.
3. `src/gui/workers.py` runs detection, highlight ranking, section download, and clip processing outside the GUI thread.
4. `src/pipeline.py` runs local faster-whisper transcription, subject tracking/reframing, ASS caption generation, and final FFmpeg export.
5. `src/gui/main_window.py` exposes Process Selected and Auto-Clip Top 3 in the Pre-Recorded Clips tab.

Therefore the YouTube pre-recorded feature did not need a duplicate implementation. v1.0.4 adds explicit regression coverage for the no-heatmap audio/transcript fallback and makes the workflow clearer in the README.

## Changes in v1.0.4

- Added a standard-library-only system doctor: `python -m src.doctor` (also supports `--json`).
- Added `scripts/setup_windows.bat` for Python 3.12 environment creation, dependency installation, development-test dependencies, and diagnostics.
- Added `scripts/build_windows.bat` for dependency checks, deterministic tests, optional online/model integration tests, PyInstaller build, packaged GUI smoke test, and optional Inno Setup installer generation.
- Updated GitHub Actions Windows workflow to run the offline test suite and doctor before packaging.
- Fixed a destructive pass-through pipeline path: with reframing and captions disabled, the original source is now copied, not moved. Same-path no-op is safe; same-path processing is rejected to protect the original.
- Prevented pre-recorded exports from silently overwriting earlier clips.
- GUI now reports saved versus failed clips accurately and no longer displays duplicate failure dialogs.
- Updated YouTube integration test helpers to invoke `yt_dlp` through the active Python interpreter instead of assuming a Linux-only `.venv/bin` path.
- Updated package and installer version to 1.0.4.

## Tests executed in this environment

Environment: Linux x86_64, Python 3.13.5, FFmpeg/ffprobe 7.1.5, 5.8 GiB RAM. The sandbox did not have the full app dependency set installed.

| Test group | Result |
|---|---:|
| Core offline suite: doctor, pipeline, framing, ingestion unit tests, highlight ranking, live chat | 41 passed, 4 deselected |
| Live monitor non-real-time tests | 3 passed, 1 deselected |
| Ring-buffer non-real-time tests | 6 passed, 1 deselected |
| Caption generation and FFmpeg burn tests | 11 passed, 1 deselected |
| Python compile check (`compileall`) | Passed |
| **Total executed** | **61 passed, 7 deselected** |

The deselected tests require live YouTube access, long real-time stream playback, or a real Whisper/model download.

## Not certified in this sandbox

The following checks were not run because the required dependencies or Windows environment were unavailable:

- Full PySide6 GUI test suite and packaged GUI smoke test.
- Real YouTube metadata probe and real section download.
- Real faster-whisper transcription/model download.
- MediaPipe face detection and ONNX/YOLO person detection with their runtime packages.
- Live stream resolution and real chat monitoring.
- Windows PyInstaller executable and Inno Setup installer build.
- NVIDIA CUDA performance benchmark.

The doctor correctly reported FFmpeg and ffprobe as available, recommended the Lite profile for this 5.8 GiB sandbox, and reported the missing application packages. This is an environment limitation, not a claim that those dependencies are missing on the user's PC.

## Windows release steps

1. Install Python 3.12 and FFmpeg, with both `ffmpeg` and `ffprobe` on PATH.
2. Run `scripts\\setup_windows.bat`.
3. Run `scripts\\build_windows.bat`.
4. For live YouTube and real AI-model integration checks, set `CUT2CLIP_RUN_ONLINE_TESTS=1` before running the build script, after network access is available.
5. The portable EXE is written to `dist\\cut2clip.exe`. If Inno Setup is installed, the installer is written under `installer\\`.

A Windows EXE/installer is not included in this source ZIP because this build environment could not run or certify a Windows build.
