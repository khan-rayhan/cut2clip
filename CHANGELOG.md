# Changelog

## v1.0.1 — 2026-11-20

### Fixed
- Windows: captions failed to burn because the `.ass` path (`C:\...`) was passed to the ffmpeg filter unquoted. The path is now quoted and escaped.
- Split-screen layout stretched the picture (a round object came out 1.74x too tall on top and 0.80x too squat below). Panels now keep the source aspect ratio; the top panel sits on a blurred copy instead of being stretched.
- Live mode saved raw 16:9 cuts. Every live clip now goes through reframe and captions. Cutting and processing run in separate workers so a slow render never lets the 80s buffer expire. A failed or interrupted clip keeps its raw cut as `<name>-raw.mp4`.
- The audio fallback downloaded the whole audio track to disk. It is now streamed through ffmpeg and scored in memory (`ingestion.download_audio` is replaced by `ingestion.audio_stream_source`; the CLI `--keep-audio` option is removed).
- `download_section` now checks the result with ffprobe and deletes it with an error if the file is far longer than requested.
- `process_clip` and `Framer.reframe_video` used fixed temp file names, so two clips processed at once overwrote each other.
- Closing the GUI or stopping the monitor no longer destroys a running worker thread, and the live buffer folder is deleted when monitoring stops.

## v1.0.0 — 2026-11-18

First release. A desktop app (Windows first, macOS second) that
turns video and live stream URLs into 40-second vertical
Shorts/Reels (9:16, 1080x1920, H.264/AAC, MP4).

### Added
- URL input with automatic VOD vs live detection (yt-dlp).
- Mode A (VOD): Most Replayed heatmap extraction, with an audio
  energy plus transcript hook-density fallback; non-overlapping
  40-second windows around the peaks.
- Mode B (live): chat velocity monitoring (Z-score > 2.5),
  80-second rolling ring buffer, 40-second clip per spike
  (t-20s to t+20s).
- Auto-framing: MediaPipe face detection with EMA smoothing,
  YOLOv8n (ONNX Runtime) fallback, split-screen for multiple
  speakers.
- Auto-captions: faster-whisper word timestamps, Hormozi-style
  pop-up subtitles burned in with FFmpeg.
- PySide6 GUI: detect, VOD clip list, live monitor, job queue,
  progress, finished-clip list, persistent settings.
- PyInstaller one-file build (Windows guide in
  `packaging/build-windows.md`).

### Fixed during final verification
- `download_section` downloaded the whole video instead of the
  40-second window: the Python API has no `download_sections`
  option — the CLI strings map to a `download_ranges` callback.
  Also capped formats to 720p MP4 (uncapped picked a 229 MB 4K
  AV1 file; generic `bv*+ba` picked webm that stalls on some
  proxies).
- `process` failed at the last step when the output folder was
  on a different filesystem from /tmp (`os.replace` cannot
  rename across filesystems). The final move now uses
  `shutil.move`.
- The bundle spec now also collects libEGL/libGLESv2 from the
  durable `~/mediapipe-libs` copies, so a VM replacement no
  longer produces a bundle that fails at startup with
  "ImportError: libEGL.so.1".

### Known issues
- The real live-stream run could not be completed on the build
  VM (streamlink cannot reach YouTube through the VM's proxy);
  monitor logic is proven by synthetic burst tests. First live
  run on a real PC is a manual check.
- The macOS build is untested (no Mac was available).
- First launch of the one-file bundle is slow (it unpacks
  itself); Whisper models download on first use (~75 MB for
  tiny).
- MediaPipe prints a harmless `TypeError: 'NoneType' object is
  not callable` warning from its FaceDetector teardown at
  shutdown. It does not affect the output.
- Facebook live chat is not supported in v1 (needs login/API
  approval). YouTube and Twitch first.
