# Phase 2 — Live rolling buffer and spike detector

## Goal
Watch a live stream, detect chat spikes in real time, and save a
40-second clip from 20 seconds before each spike to 20 seconds
after it. No GUI yet. Command line only.

## Verified facts (research done 2026-11-18)
- streamlink 8.6.3 and chat-downloader are installed in
  `shorts-app/.venv` and their CLIs respond.
- This VM sits behind a MITM egress proxy. `certifi` (pulled in by
  streamlink/chat-downloader) lacks the proxy CA, so yt-dlp fails
  with CERTIFICATE_VERIFY_FAILED on some hosts while plain urllib
  succeeds. Fixed in `src/ingestion.py`: on a certificate error the
  probe retries once with `nocheckcertificate` and warns. The same
  proxy flakiness can hit streamlink and chat-downloader, so the
  live end-to-end test may need to run on the user machine.
- Chat velocity is computed on message arrival time, not on the
  source timestamp field, so it works for every chat source.

## Tasks

### 2.1 Chat velocity monitor (`src/live_chat.py`)
- `ChatVelocity` class: feed arrival timestamps, keep per-second
  counts in a rolling window.
- `zscore(window_s=10, baseline_s=300)`: current window rate vs the
  rolling mean and standard deviation of earlier per-second rates.
- Trigger when z-score is above 2.5, the current 10-second window
  holds at least 10 messages, and at least 60 seconds of baseline
  exist. A 45-second cooldown follows every trigger.
- `iter_live_chat(url)`: generator over chat-downloader messages as
  they arrive, with reconnect and a clear error when the source
  cannot be opened.
- Check: synthetic flat chat never triggers; synthetic chat with a
  burst at 120s triggers once near 120s with z above 2.5; a second
  burst inside the cooldown does not trigger.

### 2.2 Rolling ring buffer (`src/ring_buffer.py`)
- `resolve_stream_url(url)`: streamlink Python API returns the best
  HLS URL for the stream. A direct HLS URL is accepted as-is.
- `RingBuffer`: runs ffmpeg writing 10-second segments with
  `-f segment -segment_time 10 -segment_wrap 8`, stream copy, so
  the last 80 seconds are always on disk. Each segment is stamped
  with its wall-clock start time.
- `extract_clip(start_ts, end_ts, out_path)`: concatenates the
  segments covering the window and re-encodes to H.264/AAC so the
  cut lands exactly on the requested times.
- Check: with a local file as the source, after 90 seconds of
  recording the buffer holds at least 60 seconds, and extracting
  the last 40 seconds produces a file of 40 seconds with video
  and audio.

### 2.3 Live monitor (`src/live_monitor.py`)
- Starts the buffer and the chat reader in threads, feeds arrival
  times into `ChatVelocity`, and on a trigger extracts
  [t-20s, t+20s] to the output folder.
- Names clips by spike time and message count. Logs every trigger
  and every failure, and never lets one failed clip stop the run.
- Check: with a scripted chat feed (burst at a known time) and a
  local file as the stream source, a clip is saved covering the
  burst window.

### 2.4 CLI and tests (`src/cli.py`, `tests/`)
- `live <url> [--seconds N] [--out DIR] [--z 2.5] [--dry-run]`:
  monitor for N seconds (default: until stopped), print spikes,
  save clips unless `--dry-run`.
- Tests cover 2.1 on synthetic data and 2.2 plus 2.3 on a local
  file source. A real live stream run is a manual check on the
  user machine when a stream is live.
- Check: `python -m pytest tests/` passes and the `live` command
  starts, prints status lines, and stops cleanly.

## Waves
- Wave 1: 2.1 (velocity, pure logic, no network).
- Wave 2: 2.2 (buffer, local file source first).
- Wave 3: 2.3, 2.4 (monitor plus CLI, depend on 2.1 and 2.2).

## Verification criteria
- Every check above passes.
- No clip is shorter than 39 seconds or longer than 41 seconds.
- No two saved clips overlap in stream time.
- A flat chat produces zero clips; a spiking chat produces one
  clip per spike outside the cooldown.

## Out of scope for this phase
- Auto-framing and captions (Phase 3).
- Any GUI (Phase 4).
- Facebook live chat (needs login and API approval, after v1).
