# Cut2Clip

Cut2Clip is a free, open-source desktop app for Windows (macOS
second) that turns video and live stream URLs into ready-to-post
40-second vertical Shorts and Reels (9:16, 1080x1920, H.264/AAC,
MP4).

Paste a link and it does the rest: for recorded videos it finds the
best moments from YouTube's Most Replayed heatmap, boosted by
comment spikes — moments lots of viewers commented on with a
timestamp ("1:23", "1:02:03") count extra (with an audio-energy and
transcript fallback when there is no heatmap); for live streams it
watches the chat and cuts a 40-second clip around every spike. Each
clip is auto-framed on the speaker with MediaPipe and YOLOv8,
smoothed so the camera never jumps, and captioned word by word in
your choice of Hormozi, TikTok, karaoke or neon style with
faster-whisper — all running locally on your PC, no cloud, no
watermark, no subscription.

Just install, paste a link, and your clips are ready. Built with the
GSD workflow — see `.planning/`.

## Status
- **v1.0.2** (2026-11-20) — adaptive performance profiles and single-pass video encoding. Earlier phase verification remains documented below.
- **Phase 1 done**: ingestion plus highlight detection.
- **Phase 2 done**: live rolling buffer plus chat spike detector
  (Z-score > 2.5, 45s cooldown, 40s clip per spike).
- **Phase 3 done**: auto-framing (MediaPipe + YOLOv8n via ONNX
  Runtime) and Hormozi-style captions (faster-whisper).
  Demo: `demo/rick-vertical-15s.mp4`.
- **Phase 4 done**: PySide6 GUI plus PyInstaller packaging
  (one-file bundle, smoke-tested).
- **Phase 5 done**: full verification — 74 tests pass, a real
  40-second pre-recorded clip processed end to end
  (`demo/rick-40s-vertical.mp4`: 1080x1920, H.264/AAC, exactly
  40.000s, face-centred framing, Hormozi captions burned in).
  See `.planning/phase-5/VERIFICATION.md`.
- Full changelog: `CHANGELOG.md`.

## Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest  # for tests
```

## Desktop app
```bash
.venv/bin/python -m src.gui_main
```
Paste a URL, press Detect. A pre-recorded video shows its ranked 40-second
highlight windows — tick the ones you want and press Process
selected, or press Auto-clip top 3 to process the best three at
once with no ticking. A live stream shows the monitor tab — Start monitoring
and clips appear as chat spikes. Settings (output folder, Whisper model, performance mode, caption style, device, Z threshold) are remembered between runs.

Pre-recorded ranking uses YouTube's Most Replayed heatmap boosted
by comment spikes: comments that mention a timestamp ("1:23",
"1:02:03") vote for that moment, so a scene viewers kept
commenting on outranks a slightly stronger replay peak nobody
mentioned. At most 100 comments are fetched (no API key, plain
yt-dlp); when comments are disabled or unavailable the heatmap
alone is used.

## Command line
```bash
# Show metadata for a URL (pre-recorded vs live, heatmap, captions)
.venv/bin/python -m src.cli probe "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Ranked 40-second highlight windows (heatmap + comment spikes, else audio + transcript fallback;
# the audio is streamed and scored in memory, never saved)
.venv/bin/python -m src.cli clips "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -n 3

# Monitor a live stream for chat spikes (saves finished 9:16 captioned clips;
# add --no-process for raw 16:9 cuts, --model small for better captions)
.venv/bin/python -m src.cli live "<live url>" --seconds 600 --out live-clips

# Reframe a local clip to 1080x1920 and burn captions
# (--caption-style hormozi|tiktok|karaoke|neon, default hormozi)
.venv/bin/python -m src.cli process input.mp4 --out vertical.mp4 --model tiny
```

## Build the Windows exe
See `packaging/build-windows.md`. In short:
```powershell
pyinstaller cut2clip.spec
# -> dist\cut2clip.exe
```

## Layout
```
src/
  ingestion.py    yt-dlp probe, pre-recorded/live detection, audio/section download
  highlights.py   heatmap peaks, audio energy, transcript hooks, windows
  live_chat.py    chat velocity (Z-score) and live chat reader
  ring_buffer.py  rolling 80s buffer via streamlink + ffmpeg
  live_monitor.py spike -> 40s clip monitor
  framing.py      MediaPipe/YOLOv8 subject tracking, 9:16 reframe
  captions.py     faster-whisper word timestamps, ASS captions, burn-in
  pipeline.py     process_clip: reframe + captions for one clip
  performance.py  hardware-aware Lite/Balanced/Fast profiles and FFmpeg encoder selection
  cli.py          probe, clips, live, process commands
  gui/            PySide6 main window and QThread workers
  gui_main.py     desktop entry point (--smoke-test for packaging)
tests/            pytest suite (74 tests, incl. offscreen GUI tests)
.planning/        PROJECT.md REQUIREMENTS.md ROADMAP.md STATE.md phase-N/PLAN.md
packaging/        build-windows.md
```

## Known issues
- The real live-stream run could not be completed on the build
  VM (streamlink cannot reach YouTube through the VM's proxy);
  monitor logic is proven by synthetic burst tests. First live
  run on a real PC is a manual check (see
  `.planning/phase-5/VERIFICATION.md`).
- CUDA is not verified yet: the Device and Performance settings are
  now wired through (GUI, CLI and live), and faster-whisper detects
  CUDA via CTranslate2 without PyTorch, but caption speed on a real
  NVIDIA GPU is still unmeasured, and the Windows bundle ships
  CPU-only ctranslate2 unless a CUDA build is installed.
- First launch of the one-file bundle is slow (it unpacks
  itself); Whisper models download on first use (~75 MB for
  tiny).
- MediaPipe prints a harmless `TypeError: 'NoneType' object is
  not callable` warning from its FaceDetector teardown at
  shutdown. It does not affect the output.
- Facebook live chat is not supported in v1 (needs login/API
  approval). YouTube and Twitch first.
- The macOS build is untested (no Mac was available).

## Notes
- Only process URLs you have the right to clip.
- Live mode needs the machine on and the stream running.
- On an NVIDIA GPU, YOLO prefers CUDAExecutionProvider when
  available and faster-whisper uses CUDA when CTranslate2 reports a
  GPU; a CUDA-enabled ctranslate2 build is needed for GPU captions
  on Windows. CPU fallback works everywhere.
  On this VM's CPU a 40-second clip takes a few minutes; the
  exact timing is in `.planning/phase-5/VERIFICATION.md`.

## Performance modes

Cut2Clip now supports adaptive processing profiles:

- **Auto** chooses Lite on systems with 8 GB RAM or less / 4 CPU cores or less, Fast on systems with at least 24 GB RAM and 8 cores, and Balanced otherwise.
- **Lite** reduces AI frame sampling and detection resolution, limits FFmpeg CPU threads, and uses the tiny Whisper model when no model is explicitly selected.
- **Balanced** provides a middle ground for everyday laptops and desktops.
- **Fast** uses denser subject sampling and a faster software encoding preset.

FFmpeg probes for a working NVIDIA NVENC, Intel Quick Sync, or AMD AMF H.264 encoder and uses one when available. If no hardware encoder passes the probe, it falls back to tuned x264 software encoding. Whisper model instances are cached between clips, CPU inference uses int8, and decoding uses greedy beam size 1 with VAD to reduce work on short clips.

When reframing and captions are both enabled, the vertical frames and ASS captions are sent through one FFmpeg encode rather than encoding the video once for reframing and again for captions. The final resolution remains 1080×1920.

CLI example:

```bash
python -m src.cli process input.mp4 --performance lite --device auto --model tiny
```
