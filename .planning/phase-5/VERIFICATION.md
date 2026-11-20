# Phase 5 — Requirements verification

Evidence for every requirement in `../REQUIREMENTS.md`. Status:
**verified** (evidence in hand), **pending** (check still
running), **gap** (honest limitation, carried to known issues).

## Functional

| Req | Status | Evidence |
|-----|--------|----------|
| FR1 — URL in GUI, VOD vs live detection | verified | `tests/test_ingestion.py` (real probe: Rick Astley, is_live False); `tests/test_gui.py::test_probe_worker_mocked` + `test_window_detect_invalid_url`; CLI `probe` runs on a VOD and on a live stream (Lofi Girl, Live: True, 2026-11-18). |
| FR2 — Most Replayed heatmap | verified | Real probe returns 100 heatmap points (peak 1.0); `tests/test_highlights.py` (synthetic + real); CLI `clips` returned 2 heatmap windows. |
| FR3 — audio + transcript fallback | verified | Real fallback run on downloaded audio: 3 windows, all source `audio`; `tests/test_highlights.py` (audio energy + hook density). |
| FR4 — distinct non-overlapping 40s clips | verified | `tests/test_highlights.py` (min-gap, overlap rejection); real `clips` run dropped the overlapping third peak. |
| FR5 — live chat sliding-window frequency | verified | `tests/test_live_chat.py`: flat chat never triggers; burst triggers once with z > 2.5. |
| FR6 — rolling buffer ≥ 60s | verified | `tests/test_ring_buffer.py`: buffer retains ≥ 60s (8 × 10s segments = 80s). |
| FR7 — Z > 2.5 trigger, t-20s to t+20s | verified | `tests/test_live_monitor.py`: monitor saves one 40s clip per burst; cooldown blocks the second burst. |
| FR8 — auto-framing, EMA smoothing | verified | `tests/test_framing.py` (ema_smooth, crop_x, synthetic reframe exactly 1080x1920); MediaPipe finds a real face in a talking-head clip; demo `demo/rick-vertical-15s.mp4` shows the face centred. |
| FR9 — split-screen for multi-speaker | verified | `tests/test_framing.py::test_decide_layout` (split when ≥ 2 faces for ≥ 3s of samples). Real multi-speaker footage not run end to end — layout logic only. |
| FR10 — faster-whisper word captions, Hormozi ASS, burn-in | verified | `tests/test_captions.py` (event count = word count, yellow current word, burn changes pixels); real transcription: 42 words, actual lyrics; demo frame shows "I feel commitment" burned in. |
| FR11 — every clip 1080x1920, H.264/AAC, MP4, 40s | verified | `demo/rick-40s-vertical.mp4`: ffprobe h264 1080x1920 + aac, duration 40.000s. Frames at 10s and 30s viewed: subject in frame, Hormozi captions burned in with the current word yellow ("We **don't** think", "If I'm **gonna**"). |
| FR12 — GUI: input, mode, queue, progress, finished clips, open output | verified | `tests/test_gui.py` (window constructs, outputs list, double-click opens via QDesktopServices); `--smoke-test` builds the window; packaged bundle smoke test passes. |

## Non-functional

| Req | Status | Evidence |
|-----|--------|----------|
| NFR1 — Windows 10/11 first, macOS second, one codebase | verified (Windows) / gap (macOS) | Single Python codebase (PySide6). Windows build documented in `packaging/build-windows.md`; Linux bundle built and smoke-tested. No Mac was available, so the macOS build is untested — recorded as a known issue. |
| NFR2 — all processing local | verified | By architecture: faster-whisper, YOLOv8, MediaPipe, FFmpeg all run locally. The only network traffic is the source download itself and live chat. |
| NFR3 — CPU-only finishes a 40s clip in reasonable time | verified | `process` step: 5m09s real on this VM's CPU (tiny model); section download ~1 min on top. GPU path (CUDA) is code-present and auto-selected, untested here (VM is CPU-only) — on the user's NVIDIA PC it will be much faster. |
| NFR4 — a failed clip must not kill the queue | verified (code) | `MainWindow._on_clip_failed` shows the error and calls `_process_next()`; the worker emits `failed` and never raises into Qt. No dedicated test for queue continuation — noted, not hidden. |
| NFR5 — clips from one source never overlap | verified | `tests/test_highlights.py` (overlap rejection); real runs confirm. |

## Fix list

| # | Found | Fix | Re-run |
|---|-------|-----|--------|
| 1 | `download_section` downloaded the whole 213s video instead of the 40s window | Root cause: the Python API has no `download_sections` option — the CLI's `--download-sections` strings map to a `download_ranges` CALLBACK. Also capped formats to 720p MP4 (uncapped picked a 229 MB 4K AV1 file; generic `bv*+ba` picked stalling webm). Fixed in `src/ingestion.py`; regression test `test_download_section_cuts_exact_window` added | `test_ingestion.py`: 2 passed; 40s source verified h264+aac, 40.000s |
| 2 | Full suite collection failed: PySide6 import needs libEGL, and the /usr/lib copies vanished in a VM replacement | Dev runs now export LD_LIBRARY_PATH to `~/mediapipe-libs` before starting Python; recorded in `~/AGENTS.md` | Full suite: 31 passed (11 min, incl. the 2 slow tests). The new section-cut regression test passed separately — 32 tests total, all green. |
| 3 | `process` failed at the last step: reframe (40.000s), ASS and caption burn (40.000s) all succeeded, but the final move to the output folder failed — `os.replace` across filesystems ("Invalid cross-device link": temp files in /tmp tmpfs, output on the main disk). This would have broken every GUI job saving outside /tmp. | Replaced `os.replace` with `shutil.move` in `src/pipeline.py` (copies across filesystems); regression test `test_process_clip_output_on_other_filesystem` added | **Resolved** — re-run exited 0, `demo/rick-40s-vertical.mp4` written (1080x1920, 40.000s). The pipeline tests (incl. the new cross-device test) passed before the re-run. |

## Manual checks for the user (on their own PC)
- First live run: start the GUI, paste a live Twitch/YouTube URL, Start monitoring, confirm clips appear on a real chat spike.
- Windows build: follow `packaging/build-windows.md`, run the exe, confirm the window opens and a VOD detect works.
- macOS build: same spec on a Mac (untested).
