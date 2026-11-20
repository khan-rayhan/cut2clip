# Shorts App — Requirements

## Functional
- FR1: Accept a video URL in the GUI and detect VOD vs live with yt-dlp.
- FR2: Mode A extracts Most Replayed heatmap data from yt-dlp JSON metadata.
- FR3: Mode A falls back to audio energy peaks plus transcript
  sentiment and hook density when no heatmap exists.
- FR4: Mode A cuts as many distinct non-overlapping 40-second clips as
  the peaks allow, each centred on or starting just before its peak.
- FR5: Mode B connects to live chat and measures message frequency with
  a sliding window (per second and per minute).
- FR6: Mode B keeps a rolling video/audio ring buffer of at least the
  last 60 seconds via streamlink plus FFmpeg segmented HLS.
- FR7: Mode B triggers on chat velocity Z-score above 2.5 and captures
  t-20s to t+20s, 40 seconds total.
- FR8: Auto-framing detects the active speaker or primary subject and
  crops to 1080x1920 with EMA smoothing so the frame never jumps.
- FR9: Multi-speaker or screen-share input uses a split-screen layout
  (speaker at the bottom, content at the top).
- FR10: Auto-captions come from faster-whisper word-level timestamps,
  rendered as Hormozi-style pop-up ASS subtitles and burned in.
- FR11: Every clip is 1080x1920, H.264/AAC, MP4, 40 seconds.
- FR12: The GUI shows input, mode, job queue, progress, and finished
  clips, and opens the output folder.

## Non-functional
- NFR1: Runs on Windows 10/11 first, macOS second, from one codebase.
- NFR2: All processing is local. No video leaves the machine except
  the source download itself.
- NFR3: CPU-only machines must still finish a 40-second clip in
  reasonable time; GPU, when present, speeds up whisper and detection.
- NFR4: A failed clip must not kill the queue; the job reports its
  error and the next job continues.
- NFR5: Clips from one source must never overlap in time.

## Out of scope for v1
- Facebook live chat, TikTok live, direct social auto-posting.
- Cloud rendering, accounts, or sync.
- Paid caption styles beyond the built-in Hormozi-style preset.
