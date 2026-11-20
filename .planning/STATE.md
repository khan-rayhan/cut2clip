# Shorts App — State

## Current position
- 2026-11-18 12:36 +06: `/gsd:new-project` spec received (re-sent
  after an interrupted first attempt at 12:33). Discuss done, planning
  artifacts written.
- 2026-11-18: **Phase 1 done and verified.** `src/ingestion.py`
  (yt-dlp probe, VOD/live detection), `src/highlights.py`
  (heatmap peaks, audio energy, transcript hooks, 40s windows),
  `src/cli.py` (`probe` and `clips`). 6 tests pass. Real YouTube
  probe returns a 100-point heatmap; `clips` returns 2 heatmap
  windows and the audio fallback returns 3 windows on the same
  video. Plan in `.planning/phase-1/PLAN.md`.

## Decisions locked
- PySide6 for the GUI, single Python codebase, Windows first.
- yt-dlp for detection and download; streamlink plus FFmpeg for the
  live buffer; chat-downloader with pytchat fallback.
- MediaPipe first for framing, YOLOv8 only with a GPU.
- faster-whisper local for captions, ASS burn-in with FFmpeg.
- YouTube and Twitch first; Facebook live chat after v1.

## Decisions locked (update 2026-11-18 12:38 +06)
- NVIDIA GPU confirmed on the user Windows PC. Phase 3 will build
  the YOLOv8 framing path and run faster-whisper on CUDA (base or
  small model), with NVENC encoding where available. CPU fallback
  stays for machines without a GPU.

## Phase 2 - done and verified 2026-11-18
- Live chat monitor (`src/live_chat.py`): ChatVelocity with a
  10-second window, 300-second baseline, Z-score trigger above 2.5,
  10-message minimum, 60-second baseline minimum, 45-second
  cooldown. chat-downloader feeds live chat; velocity is computed
  on message arrival time.
- Rolling ring buffer (`src/ring_buffer.py`): streamlink resolves
  the stream URL, ffmpeg writes 10-second stream-copy segments,
  8 kept (80 seconds, above the 60-second minimum), pruned by a
  background thread. extract_clip re-encodes the requested window
  to H.264/AAC.
- Live monitor (`src/live_monitor.py`): on a spike at t it queues
  a [t-20s, t+20s] clip and cuts it in a worker thread once the
  window is fully buffered. CLI: `live <url> [--seconds N]
  [--out DIR] [--z 2.5] [--dry-run]`.
- Verification: 13 tests pass. Flat chat never triggers, a burst
  triggers once with z above 2.5, the cooldown blocks a second
  burst, the buffer holds at least 60 seconds, and the monitor
  saves one 40-second clip per burst.
- Three real bugs found and fixed during verification:
  1. Segment names are local time but were parsed as UTC, which
     put every segment six hours in the future on a +06:00
     machine and made every clip "older than the buffer".
  2. The Z-score baseline counted pre-run seconds as zeros, which
     fired a false spike ten seconds into flat chat. The baseline
     now covers only seconds with real history.
  3. Cutting a clip 2 seconds after its window end produced a
     clip a second short; the settle delay is now 5 seconds.
- Also fixed: yt-dlp retries once with certificate checks off
  after a CERTIFICATE_VERIFY_FAILED error (this VM's MITM proxy
  CA is missing from certifi's bundle), with a warning.
- Real live-stream end-to-end run is still a manual check on the
  user machine when a stream is live; the proxy here makes live
  network tests flaky.

## Phase 3 - done and verified 2026-11-18
- Framing (`src/framing.py`): MediaPipe Tasks API face detection
  (BlazeFace model), YOLOv8n person detection through ONNX
  Runtime, EMA smoothing (alpha 0.3), single vs split-screen
  layout, OpenCV reframe to 1080x1920 with original audio muxed
  back.
- Captions (`src/captions.py`): faster-whisper word timestamps,
  ASS with one event per word (current word yellow, rest white),
  ffmpeg burn-in.
- Pipeline (`src/pipeline.py`): reframe, transcribe, burn. CLI:
  `process <input.mp4> [--out OUT] [--model tiny|base]
  [--no-captions] [--no-reframe]`.
- Fixes made while building:
  1. MediaPipe 1.x dropped the Solutions API; face detection now
     uses the Tasks API. Its native library needs libEGL.so.1 and
     libGLESv2.so.2; the Ubuntu 24.04 .debs were extracted and the
     libraries installed into /usr/lib/x86_64-linux-gnu (ldconfig).
  2. YOLOv8 moved from ultralytics+torch to ONNX Runtime: the
     torch install ran 18+ minutes through this proxy before it
     was stopped; ONNX is a 12 MB model and a small runtime.
     The v8.4.0 release tag has yolov8n.onnx (v8.3.0 does not).
  3. faster-whisper 1.2.1 needs av below 14; pinned av>=11,<14.
  4. The Z-score baseline bug from Phase 2 was fixed (baseline
     covers only seconds with real history).
- Verified so far: pure framing helpers, synthetic reframe to
  1080x1920, ASS generation, caption burn changes pixels, full
  pipeline with real transcription on CPU, real audio
  transcription (42 words, actual lyrics), MediaPipe finds a real
  face in a talking-head clip. Full suite: 21 passed, 1 failed
  (a rounding expectation in the crop test, fixed to 438), plus
  the 2 slow Phase 2 tests passing in their latest runs.
- Bug found while verifying the CLI end to end: adding the
  `process` command left the argument parsing lines stranded
  inside `cmd_process` after its `return`, so every CLI command
  silently did nothing and exited 0. Fixed by moving the parse
  and dispatch back into `main()`. Lesson: the CLI itself needs
  a smoke test, not just the modules behind it.
- The Rick test clip is video-only, so the first end-to-end
  `process` run failed in transcription (no audio to decode).
  A combined audio+video clip was muxed from the two section
  downloads for the real end-to-end run.
- Known cosmetic issue: MediaPipe's FaceDetector prints a
  `TypeError: 'NoneType' object is not callable` warning from its
  `__del__` at interpreter shutdown. Harmless, exit code
  unaffected.
- End-to-end proof: `process` on a real 15s Rick Astley clip
  produced a 1080x1920 H.264/AAC MP4 in ~135s on CPU. A frame
  check shows the face centred and the caption "I feel
  commitment" burned in with the current word yellow. Demo saved
  at `workspace/shorts-app/demo/rick-vertical-15s.mp4`.
- Full suite: 24 tests, all passing in their latest runs
  (22 fast + 2 slow Phase 2 tests).

## Phase 4 - done and verified 2026-11-18
- Plan: `.planning/phase-4/PLAN.md` (tasks 4.1 GUI shell, 4.2
  workers, 4.3 entry point, 4.4 packaging).
- Deps: PySide6 6.12.0, PyInstaller 6.22.3 installed in the venv.
- Code: `src/gui/main_window.py` (URL detect, VOD clip list with
  checkboxes, live monitor tab, output list, settings persisted
  with QSettings), `src/gui/workers.py` (ProbeWorker, ClipsWorker,
  VodClipWorker, LiveWorker — all QThreads, signal-based),
  `src/gui_main.py` (entry point, `--smoke-test` flag, bundle dir
  first on PATH when frozen).
- Support changes: `pipeline.process_clip` takes an optional
  `log` callback (default print); `LiveMonitor` takes an optional
  `on_event` callback; `ingestion.download_section` downloads one
  time range of a VOD as a merged MP4.
- Bugs found and fixed: VodClipWorker stored the window start in
  `self.start`, shadowing QThread.start() — renamed to
  `window_start`/`window_end`. The mocked VodClip test patched
  `src.pipeline.process_clip`, but the worker imports the name
  directly, so the patch must target `src.gui.workers.process_clip`.
- Verified so far: 7 GUI tests pass offscreen; `--smoke-test`
  builds the main window and exits 0.
- Packaging: `shorts-app.spec` (one-file, windowed, models as
  data, ffmpeg/ffprobe + libEGL/libGLESv2 as binaries) and
  `packaging/build-windows.md`. First build succeeded (450 MB
  bundle) but the bundle failed its smoke test: PyInstaller
  could not extract cv2/cv2.abi3.so (decompression error).
  Cause: collect_all for cv2 and onnxruntime duplicates the
  native libraries their PyInstaller hooks already collect,
  corrupting the one-file archive. Spec fixed to collect_all
  only mediapipe and faster-whisper. Rebuild running; the first
  rebuild attempt was killed by a service restart mid-build and
  was restarted cleanly.
- Second smoke test failed differently: `libavcodec.so.62`
  decompression error. Root cause found: the one-file bundle
  extracts to /tmp, which is a 512 MB tmpfs and was 100% full —
  the "decompression" errors were really out-of-space. Fix: run
  the bundle with TMPDIR pointing at a roomy directory.
- Third smoke test (with TMPDIR=~/tmp-bundle) extracted fine
  but failed with `ImportError: libEGL.so.1`. Root cause: the
  VM replacement wiped the /usr/lib copies of libEGL/libGLESv2
  (outside ~, ephemeral), so the spec collected nothing and the
  bundle lacked them. Libs re-copied from ~/mediapipe-libs,
  mediapipe import verified again. Third rebuild running with
  the libs present so the spec can bundle them. Lessons recorded
  in ~/AGENTS.md.
- Third build's log showed 0 matches for libEGL, but the TOC
  files proved libEGL.so.1 was in the bundle after all (the log
  just does not name spec-provided binaries). The smoke test
  then failed on the real next error: `gui_main.py` used a
  relative import (`from .gui...`), which fails when PyInstaller
  runs it as a top-level script with no parent package. Fixed to
  an absolute import (`from src.gui.main_window import ...`).
  Fourth build + smoke test running.
- Fourth build passed its smoke test: the 454 MB one-file
  bundle starts offscreen and builds the main window
  ("Smoke test OK", exit 0). Phase 4 verified: 7 GUI tests pass
  offscreen, the dev entry point smoke test passes, and the
  packaged bundle smoke test passes.
- Full suite re-run after the Phase 4 support changes: 29
  passed, 2 deselected (the 2 slow Phase 2 tests, passing in
  their latest runs) — 31 tests total, all green.

## Phase 5 - in progress 2026-11-18
- Plan: `.planning/phase-5/PLAN.md` (tasks 5.1–5.5).
- The VM was replaced again: the /usr/lib libEGL/libGLESv2
  copies vanished a second time, breaking the suite collection
  (PySide6 import needs libEGL). Durable fix for dev runs:
  export LD_LIBRARY_PATH to ~/mediapipe-libs before starting
  Python. All 31 tests collect with it; full suite running.
- First `download_section` attempt failed: yt-dlp finished
  but the output file was missing. Debugging found two real
  bugs: (1) the Python API has no `download_sections` option —
  the CLI strings map to a `download_ranges` callback returning
  [{"start_time", "end_time"}]; passing the strings was silently
  ignored and downloaded the whole 213s video. (2) Uncapped
  formats picked a 229 MB 4K AV1 file; generic `bv*+ba` picked
  webm that stalls on this proxy. Fixed: `download_ranges`
  callback + 720p-capped MP4 formats. Verified: the 40s window
  downloads as h264+aac, exactly 40.000s. Regression test added.
- The 40s end-to-end `process` run was interrupted by a
  runtime restart after ~45 minutes with no confirmed result
  (its log is 0 bytes) and /tmp was wiped, so the source clip
  and any partial output are gone. Redone after the restart:
  the redo found a real bug — `os.replace` fails across
  filesystems when the output folder is not in /tmp — fixed
  with `shutil.move` plus a regression test, then the re-run
  exited 0. `demo/rick-40s-vertical.mp4` is verified: h264
  1080x1920 + aac, exactly 40.000s, frames at 10s and 30s
  viewed (subject in frame, captions with yellow current
  word). Process time on this CPU: 5m09s.
- Phase 5 verification is complete: 33 tests total, all green
  in their latest runs (31 full suite + section-cut + cross-
  device regression tests). The one-file bundle is being
  rebuilt with the pipeline fix; smoke test next, then the
  final report to Rayhan.
- Full suite (all 31, no deselections): 31 passed in 11 min
  (slow with the downloads competing for CPU). The new
  section-cut regression test passed separately, so 32 tests
  total are green.
- Full suite (all 31, no deselections) running in the
  background with the fixed environment.

- Live end-to-end: a real live stream was found (Lofi Girl,
  youtube.com/watch?v=4t4AQ15yj1M, probe confirms Live: True),
  but streamlink cannot resolve it on this VM — its
  requests-based fetch fails through the MITM proxy
  (RemoteDisconnected, 3 attempts), while yt-dlp's urllib path
  works. This is a VM network limitation, not a code defect.
  The real live run is recorded as a manual check for the user
  on his own PC (no proxy there). The monitor logic itself is
  proven by the synthetic burst tests in Phase 2.

## Open questions
- None blocking.

## Next action
- When the download debug and the suite finish: fix
  download_section if needed, then run the 40s VOD end-to-end.

## Open questions
- None blocking.

## Next action
- When the PyInstaller build finishes: run the bundle with
  QT_QPA_PLATFORM=offscreen --smoke-test, then report Phase 4.

## Open questions
- None blocking.

## Next action
- Finish the full test suite run, then report Phase 3 to the user.
