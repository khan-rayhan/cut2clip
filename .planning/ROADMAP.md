# Shorts App — Roadmap

## Phase 1 — Ingestion and highlight detection
Goal: given a URL, detect VOD vs live and return ranked highlight times.
- yt-dlp metadata probe and VOD/live detection.
- Heatmap extraction from yt-dlp JSON, with audio-energy plus
  transcript fallback.
- Non-overlapping 40-second window selection around peaks.
- Deliverable: tested `ingestion` and `highlights` modules plus a
  command line run that prints clip windows for a sample URL.

## Phase 2 — Live rolling buffer and spike detector
Goal: watch a live stream and capture 40-second clips on chat spikes.
- Live chat monitor (chat-downloader, pytchat fallback) with sliding
  window velocity and Z-score trigger above 2.5.
- Rolling ring buffer with streamlink plus FFmpeg segmented HLS,
  at least 60 seconds retained.
- Spike capture from t-20s to t+20s.
- Deliverable: tested `live` modules plus a monitored test stream run.

## Phase 3 — Auto-framing and caption pipeline
Goal: turn any 40-second source segment into a finished vertical clip.
- MediaPipe face detection with EMA smoothing, YOLOv8 path when a
  GPU is present, split-screen layout for multi-speaker and
  screen-share.
- faster-whisper word timestamps, Hormozi-style ASS subtitles,
  FFmpeg burn-in.
- Output check: 1080x1920, H.264/AAC, MP4, 40 seconds.
- Deliverable: tested `pipeline` module plus finished sample clips.

## Phase 4 — Desktop GUI
Goal: PySide6 app that wires phases 1 to 3 together.
- URL input with VOD/live detection, mode selection, job queue,
  progress, preview, settings, output folder.
- Background workers so the UI never freezes during a render.
- PyInstaller packaging for Windows, then macOS.
- Deliverable: installable app build plus a guided first run.

## Phase 5 — Verify and ship v1
Goal: end-to-end proof on real URLs, then release.
- Full run: one YouTube VOD and one Twitch live stream, clips
  watched start to finish.
- Fix list from verification, re-run until clean.
- Deliverable: v1 build, README, and known-issues list.

## Status
- Phase 0 (new-project): done 2026-11-18. Discuss and planning
  artifacts written.
- Phase 1: done and verified 2026-11-18 (6 tests pass, real video
  probe and clips work, audio fallback verified).
- GPU: NVIDIA confirmed 2026-11-18. Phase 3 uses the YOLOv8 path
  and faster-whisper on CUDA, with a CPU fallback.
- Phase 2: done and verified 2026-11-18 (13 tests pass: spike
  detection, 80-second ring buffer, 40-second clip per burst).
- Phase 3: done and verified 2026-11-18 (24 tests pass; real
  15s clip reframed to 1080x1920 with captions burned in).
- Phase 4: done and verified 2026-11-18 (GUI + workers + entry
  point; 7 offscreen GUI tests pass; 454 MB one-file bundle
  passes its smoke test).
- Phase 5: done and verified 2026-11-18 (33 tests pass; real
  40s VOD clip processed end to end and watched via sampled
  frames; live run is a manual check on the user's PC —
  streamlink cannot reach YouTube through the VM's proxy).
  v1.0.0 shipped: bundle rebuilt with all Phase 5 fixes
  (458 MB), smoke test passes ("Smoke test OK: main window
  built.").
