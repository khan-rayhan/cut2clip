# Shorts App — Project Context

## Vision
A desktop app for Windows and macOS that turns any video URL or live
stream URL into ready-to-post 40-second vertical Shorts/Reels
(9:16, 1080x1920, H.264/AAC, MP4), with no manual editing.

## Two modes
- **Mode A — VOD:** Paste a pre-uploaded video URL. The app finds the
  best moments from the Most Replayed heatmap (yt-dlp metadata), with
  an audio-energy + transcript fallback, and cuts non-overlapping
  40-second clips around the peaks.
- **Mode B — Live:** Paste an active live stream URL. The app watches
  chat velocity in real time, keeps a rolling buffer of at least the
  last 60 seconds, and on a chat spike (Z-score > 2.5) captures a
  40-second clip from 20 seconds before the spike to 20 seconds after.

## Per-clip pipeline
1. Auto-framing to 9:16 with subject tracking and EMA smoothing,
   split-screen layout when several speakers or a screen share are present.
2. Auto-captions from faster-whisper word timestamps, Hormozi-style
   pop-up subtitles in ASS format, burned in with FFmpeg.
3. Output: 1080x1920, H.264/AAC, MP4, 40 seconds.

## Locked decisions
- UI framework: **PySide6** (Qt6). One language for the whole app,
  mature desktop widgets, PyInstaller packaging on Windows and macOS.
  Tauri plus Python was rejected: two runtimes and IPC for no gain.
  CustomTkinter was rejected: too thin for a job queue, progress,
  preview, and settings UI.
- Ingestion: **yt-dlp** for VOD/live detection and download,
  **streamlink** plus FFmpeg segmented HLS for the live rolling buffer.
- Chat: **chat-downloader** first (YouTube and Twitch), **pytchat**
  as the YouTube-live fallback. Facebook live chat needs login and
  API approval, so it ships after YouTube and Twitch.
- Framing: **MediaPipe Face Detection** first (CPU friendly),
  YOLOv8 only when a GPU is present. OpenCV for the frame pipeline.
- Captions: **faster-whisper** local, word-level timestamps, ASS burn-in.
- Windows first (the user is on Windows), macOS second with the same code.

## Constraints
- Only process URLs the user has the right to clip. Re-uploads of
  other creators' streams without permission can be demonetised.
- Live mode needs the machine on and the stream running; nothing is
  recorded while the app is closed.
- First version targets YouTube and Twitch. Facebook and other
  platforms follow once their chat access is solved.

## Source spec
User spec received 2026-11-18 12:33 +06 (Asia/Dhaka), re-sent 12:36 the
same day as `/gsd:new-project`. GSD workflow skill:
`~/workspace/custom-skills/gsd-workflow/SKILL.md`.
