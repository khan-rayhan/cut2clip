# Shorts App

Shorts App is a free, open-source desktop app for Windows (macOS
second) that turns video and live stream URLs into ready-to-post
40-second vertical Shorts and Reels (9:16, 1080x1920, H.264/AAC,
MP4).

Paste a link and it does the rest: for recorded videos it finds the
best moments from YouTube's Most Replayed heatmap (with an
audio-energy and transcript fallback); for live streams it watches
the chat and cuts a 40-second clip around every spike. Each clip is
auto-framed on the speaker with MediaPipe and YOLOv8, smoothed so
the camera never jumps, and captioned word by word in Hormozi style
with faster-whisper — all running locally on your PC, no cloud, no
watermark, no subscription.

Just install, paste a link, and your clips are ready. Built with the
GSD workflow — see `.planning/`.

## Status
- **v1.0.0** (2026-11-18) — all five phases done and verified.
- **Phase 1 done**: ingestion plus highlight detection.
- **Phase 2 done**: live rolling buffer plus chat spike detector
  (Z-score > 2.5, 45s cooldown, 40s clip per spike).
- **Phase 3 done**: auto-framing (MediaPipe + YOLOv8n via ONNX
  Runtime) and Hormozi-style captions (faster-whisper).
  Demo: `demo/rick-vertical-15s.mp4`.
- **Phase 4 done**: PySide6 GUI plus PyInstaller packaging
  (one-file bundle, smoke-tested).
- **Phase 5 done**: full verification — 33 tests pass, a real
  40-second VOD clip processed end to end
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
Paste a URL, press Detect. A VOD shows its ranked 40-second
highlight windows — tick the ones you want and press Process
selected. A live stream shows the monitor tab — Start monitoring
and clips appear as chat spikes. Settings (output folder, whisper
model, device, Z threshold) are remembered between runs.

## Command line
```bash
# Show metadata for a URL (VOD vs live, heatmap, captions)
.venv/bin/python -m src.cli probe "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Ranked 40-second highlight windows (heatmap, else audio + transcript fallback;
# the audio is streamed and scored in memory, never saved)
.venv/bin/python -m src.cli clips "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -n 3

# Monitor a live stream for chat spikes (saves finished 9:16 captioned clips;
# add --no-process for raw 16:9 cuts, --model small for better captions)
.venv/bin/python -m src.cli live "<live url>" --seconds 600 --out live-clips

# Reframe a local clip to 1080x1920 and burn captions
.venv/bin/python -m src.cli process input.mp4 --out vertical.mp4 --model tiny
```

## Build the Windows exe
See `packaging/build-windows.md`. In short:
```powershell
pyinstaller shorts-app.spec
# -> dist\shorts-app.exe
```

## Layout
```
src/
  ingestion.py    yt-dlp probe, VOD/live detection, audio/section download
  highlights.py   heatmap peaks, audio energy, transcript hooks, windows
  live_chat.py    chat velocity (Z-score) and live chat reader
  ring_buffer.py  rolling 80s buffer via streamlink + ffmpeg
  live_monitor.py spike -> 40s clip monitor
  framing.py      MediaPipe/YOLOv8 subject tracking, 9:16 reframe
  captions.py     faster-whisper word timestamps, ASS captions, burn-in
  pipeline.py     process_clip: reframe + captions for one clip
  cli.py          probe, clips, live, process commands
  gui/            PySide6 main window and QThread workers
  gui_main.py     desktop entry point (--smoke-test for packaging)
tests/            pytest suite (33 tests, incl. offscreen GUI tests)
.planning/        PROJECT.md REQUIREMENTS.md ROADMAP.md STATE.md phase-N/PLAN.md
packaging/        build-windows.md
```

## Known issues (v1.0.0)
- The real live-stream run could not be completed on the build
  VM (streamlink cannot reach YouTube through the VM's proxy);
  monitor logic is proven by synthetic burst tests. First live
  run on a real PC is a manual check (see
  `.planning/phase-5/VERIFICATION.md`).
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
- On a PC with an NVIDIA GPU, faster-whisper and YOLOv8 use CUDA
  automatically; on CPU they fall back, slower but working.
  On this VM's CPU a 40-second clip takes a few minutes; the
  exact timing is in `.planning/phase-5/VERIFICATION.md`.
