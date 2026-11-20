# Phase 1 — Ingestion and highlight detection

## Goal
Given a URL, detect VOD vs live and return ranked, non-overlapping
40-second highlight windows. No GUI yet. Command line only.

## Verified facts (research done 2026-11-18)
- yt-dlp 2026.10.26 installed in `shorts-app/.venv`.
- Real probe of a YouTube VOD returned a `heatmap` list of 100
  entries shaped `{"start_time": float, "end_time": float,
  "value": float}` with value normalised 0 to 1 and peak 1.0.
  `is_live` is False and `duration` is present.
- Python 3.12.3, numpy 1.26.4, ffmpeg and ffprobe are present.
- System Python is PEP 668 managed, so the project uses its own
  venv at `shorts-app/.venv`.

## Tasks

### 1.1 Project skeleton
- Files: `pyproject.toml`, `requirements.txt`, `README.md`,
  `src/__init__.py`.
- Requirements: yt-dlp, numpy. Everything else is stdlib plus ffmpeg.
- Check: `python -m pip install -r requirements.txt` succeeds in a
  fresh venv and `python -m src.cli --help` prints usage.

### 1.2 Ingestion module (`src/ingestion.py`)
- Probe a URL with `yt-dlp --dump-json --no-download` and parse the
  JSON. Return title, duration, `is_live`, heatmap list, and the
  subtitle track URLs when present.
- Raise a clear error for an unresolvable URL, a private video, or a
  missing yt-dlp binary.
- Check: probing the Rick Astley video returns `is_live` False,
  duration 213, and a 100 entry heatmap.

### 1.3 Heatmap peak picker (`src/highlights.py`)
- Smooth heatmap values with a short moving average, find local
  maxima, rank them by value.
- Build 40-second windows centred on each peak, clamp to
  `[0, duration - 40]`, and drop any window that overlaps a
  higher-ranked one.
- Check: on synthetic heatmap data with peaks at 40s, 100s and 160s
  the picker returns windows starting at 20s, 80s and 140s in rank
  order, with no overlaps.

### 1.4 Audio energy fallback (`src/highlights.py`)
- Extract mono 16 kHz audio through an ffmpeg pipe into numpy,
  compute RMS energy in 1-second windows, and rank the peaks the
  same way as 1.3.
- Check: on a synthetic audio file with loud bursts at 30s and 90s
  the fallback returns peaks near those times.

### 1.5 Transcript hook fallback (`src/highlights.py`)
- Fetch automatic captions with yt-dlp when they exist, score each
  10-second window by hook density (questions, exclamations, and a
  small hook word list), and combine with the audio score.
- When no captions exist, score from audio alone and say so.
- Check: on a video with captions the combined ranking differs from
  audio-only in a documented way; on a video without captions the
  run still succeeds.

### 1.6 CLI and tests (`src/cli.py`, `tests/`)
- `probe <url>` prints title, duration, live status, and heatmap size.
- `clips <url> [-n N]` prints ranked 40-second windows with source
  (heatmap or fallback) and peak time.
- Tests cover 1.3 and 1.4 on synthetic data and 1.2 on the real probe.
- Check: `python -m pytest tests/` passes and `clips` on the real
  video prints at least one window.

## Waves
- Wave 1: 1.1, 1.2 (skeleton plus probe).
- Wave 2: 1.3, 1.4, 1.5 (pickers, depend on 1.2 output shape).
- Wave 3: 1.6 (CLI plus tests, depends on all above).

## Verification criteria
- Every check above passes.
- No clip windows overlap, and every window is 40 seconds inside
  the video duration.
- A URL with no heatmap still returns windows through the fallback
  instead of failing.

## Out of scope for this phase
- Live chat monitoring and the rolling buffer (Phase 2).
- Auto-framing and captions (Phase 3).
- Any GUI (Phase 4).
