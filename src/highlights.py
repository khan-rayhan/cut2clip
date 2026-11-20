"""Highlight detection for Mode A (VOD).

Three ranked sources, tried in order:
1. Most Replayed heatmap from yt-dlp metadata (best signal).
2. Audio energy peaks from the downloaded audio track.
3. Transcript hook density from automatic captions, combined with (2).

Every source ends in the same shape: ranked, non-overlapping
40-second windows inside the video duration.
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import subprocess
import urllib.request

import numpy as np

from .ingestion import HeatPoint

CLIP_LEN = 40.0
SAMPLE_RATE = 16000

HOOK_WORDS = {
    "watch", "wait", "look", "insane", "crazy", "secret", "best",
    "why", "how", "never", "first", "shocking", "unbelievable",
    "amazing", "huge", "finally", "breaking", "exposed", "truth",
}


@dataclasses.dataclass
class ClipWindow:
    start: float          # seconds into the video
    end: float            # start + CLIP_LEN
    peak_time: float      # the peak this window is built around
    score: float          # 0..1, higher is a stronger highlight
    source: str           # "heatmap" | "audio" | "audio+transcript"


def _smooth(values: list[float], width: int = 3) -> list[float]:
    if width <= 1 or len(values) < width:
        return list(values)
    kernel = np.ones(width) / width
    return list(np.convolve(values, kernel, mode="same"))


def _rank_peaks(times: list[float], scores: list[float],
                top_n: int, min_gap: float) -> list[tuple[float, float]]:
    """Return the top local maxima as (time, score), best first.

    A point counts as a peak when it beats both neighbours. Picks are
    kept at least ``min_gap`` seconds apart so one spike cannot win
    twice.
    """
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    picked: list[tuple[float, float]] = []
    for i in order:
        if scores[i] <= 0:
            break
        left = scores[i - 1] if i > 0 else -1.0
        right = scores[i + 1] if i < len(scores) - 1 else -1.0
        if scores[i] < left or scores[i] < right:
            continue
        t = times[i]
        if any(abs(t - p[0]) < min_gap for p in picked):
            continue
        picked.append((t, scores[i]))
        if len(picked) >= top_n:
            break
    return picked


def select_windows(peaks: list[tuple[float, float]], duration: float,
                   clip_len: float = CLIP_LEN,
                   source: str = "heatmap") -> list[ClipWindow]:
    """Centre a clip on each peak, clamp inside the video, drop overlaps.

    ``peaks`` must already be ranked best first. Windows are returned
    in time order.
    """
    if duration is None or duration <= clip_len:
        return []
    max_start = duration - clip_len
    chosen: list[ClipWindow] = []
    for peak_time, score in peaks:
        start = min(max(peak_time - clip_len / 2.0, 0.0), max_start)
        end = start + clip_len
        if any(start < c.end - 0.5 and end > c.start + 0.5 for c in chosen):
            continue
        chosen.append(ClipWindow(start=start, end=end, peak_time=peak_time,
                                 score=score, source=source))
    chosen.sort(key=lambda c: c.start)
    return chosen


def heatmap_windows(heatmap: list[HeatPoint], duration: float,
                    top_n: int = 5,
                    clip_len: float = CLIP_LEN) -> list[ClipWindow]:
    """Windows from Most Replayed heatmap values."""
    if not heatmap or duration is None:
        return []
    times = [(p.start_time + p.end_time) / 2.0 for p in heatmap]
    values = _smooth([p.value for p in heatmap], width=3)
    peak = max(values) if values else 0.0
    if peak <= 0:
        return []
    norm = [v / peak for v in values]
    peaks = _rank_peaks(times, norm, top_n=top_n, min_gap=clip_len)
    return select_windows(peaks, duration, clip_len, source="heatmap")


def audio_energy_series(audio_path: str,
                        window_s: float = 1.0) -> tuple[list[float], list[float]]:
    """RMS energy per window from an audio file via an ffmpeg pipe.

    Returns (window centre times, RMS values). No heavy dependency:
    ffmpeg decodes to mono 16 kHz float samples, numpy does the rest.
    """
    cmd = ["ffmpeg", "-v", "error", "-i", audio_path,
           "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    per_window = int(SAMPLE_RATE * window_s)
    n = len(samples) // per_window
    if n == 0:
        return [], []
    trimmed = samples[: n * per_window].reshape(n, per_window)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    times = [(i + 0.5) * window_s for i in range(n)]
    return times, [float(v) for v in rms]


def audio_windows(audio_path: str, duration: float,
                  top_n: int = 5,
                  clip_len: float = CLIP_LEN) -> list[ClipWindow]:
    """Windows from audio energy peaks alone."""
    times, rms = audio_energy_series(audio_path)
    if not times:
        return []
    peak = max(rms)
    if peak <= 0:
        return []
    norm = [v / peak for v in rms]
    norm = _smooth(norm, width=3)
    peaks = _rank_peaks(times, norm, top_n=top_n, min_gap=clip_len)
    return select_windows(peaks, duration, clip_len, source="audio")


def fetch_transcript_events(caption_url: str) -> list[tuple[float, str]]:
    """Download a json3 caption track. Returns (start_seconds, text)."""
    with urllib.request.urlopen(caption_url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    events: list[tuple[float, str]] = []
    for ev in data.get("events", []):
        if "segs" not in ev:
            continue
        text = "".join(s.get("utf8", "") for s in ev["segs"]).strip()
        if text:
            events.append((ev.get("tStartMs", 0) / 1000.0, text))
    return events


def hook_density_score(events: list[tuple[float, str]],
                       duration: float,
                       window_s: float = 10.0) -> tuple[list[float], list[float]]:
    """Score each window by hook density: questions, exclamations and
    hook words per second of speech."""
    n = max(1, int(math.ceil(duration / window_s)))
    scores = [0.0] * n
    for start, text in events:
        b = min(int(start // window_s), n - 1)
        low = text.lower()
        hits = low.count("?") + low.count("!")
        hits += sum(1 for w in re.findall(r"[a-z]+", low) if w in HOOK_WORDS)
        scores[b] += hits
    peak = max(scores)
    norm = [s / peak for s in scores] if peak > 0 else scores
    times = [(i + 0.5) * window_s for i in range(n)]
    return times, norm


def combined_windows(audio_path: str, caption_url: str | None,
                     duration: float, top_n: int = 5,
                     clip_len: float = CLIP_LEN) -> list[ClipWindow]:
    """Fallback windows: 60 percent audio energy, 40 percent hook
    density when captions exist, audio alone when they do not."""
    times, rms = audio_energy_series(audio_path)
    if not times:
        return []
    peak = max(rms)
    if peak <= 0:
        return []
    audio = _smooth([v / peak for v in rms], width=3)
    source = "audio"
    if caption_url:
        try:
            events = fetch_transcript_events(caption_url)
            h_times, hook = hook_density_score(events, duration)
            hook_by_time = dict(zip(h_times, hook))
            combined = []
            for t, a in zip(times, audio):
                nearest = min(h_times, key=lambda x: abs(x - t))
                combined.append(0.6 * a + 0.4 * hook_by_time[nearest])
            audio = combined
            source = "audio+transcript"
        except Exception:
            pass  # captions failed: fall through with audio alone
    peaks = _rank_peaks(times, audio, top_n=top_n, min_gap=clip_len)
    return select_windows(peaks, duration, clip_len, source=source)
