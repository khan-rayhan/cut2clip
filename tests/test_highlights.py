"""Tests for the highlight pickers on synthetic data."""

import math
import struct
import wave

import pytest

from src.highlights import (
    ClipWindow,
    audio_windows,
    comment_density_points,
    heatmap_windows,
    hook_density_score,
    parse_comment_timestamps,
    select_windows,
)
from src.ingestion import HeatPoint


def _synthetic_heatmap(peaks, duration=180.0, step=2.0):
    """Heatmap with value 1.0 at the peak times, 0.1 elsewhere."""
    points = []
    t = 0.0
    while t < duration:
        value = 0.1
        for p in peaks:
            value = max(value, math.exp(-((t - p) ** 2) / (2 * 3.0 ** 2)))
        points.append(HeatPoint(t, t + step, value))
        t += step
    return points


def test_heatmap_windows_find_three_peaks():
    windows = heatmap_windows(_synthetic_heatmap([40, 100, 160]), 180.0, top_n=3)
    assert len(windows) == 3
    starts = [w.start for w in windows]
    assert starts == pytest.approx([20.0, 80.0, 140.0], abs=3.0)
    assert all(w.end - w.start == 40.0 for w in windows)
    assert all(w.source == "heatmap" for w in windows)


def test_windows_never_overlap():
    peaks = [(30.0, 1.0), (45.0, 0.9), (120.0, 0.8)]
    windows = select_windows(peaks, 180.0)
    assert len(windows) == 2  # the 45s peak overlaps the 30s window
    assert windows[0].start == pytest.approx(10.0)
    assert windows[1].start == pytest.approx(100.0)


def test_windows_clamped_to_duration():
    windows = select_windows([(175.0, 1.0)], 180.0)
    assert len(windows) == 1
    assert windows[0].end == pytest.approx(180.0)
    assert windows[0].start == pytest.approx(140.0)


def _write_burst_wav(path, duration=120.0, bursts=(30, 90), rate=16000):
    """Quiet sine with loud bursts at the given seconds."""
    frames = bytearray()
    total = int(duration * rate)
    for i in range(total):
        t = i / rate
        amp = 0.9 if any(abs(t - b) < 2 for b in bursts) else 0.05
        sample = int(amp * 32767 * math.sin(2 * math.pi * 440 * t))
        frames += struct.pack("<h", sample)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def test_audio_windows_find_bursts(tmp_path):
    audio = tmp_path / "burst.wav"
    _write_burst_wav(str(audio))
    windows = audio_windows(str(audio), 120.0, top_n=2)
    assert len(windows) == 2
    peaks = sorted(w.peak_time for w in windows)
    assert peaks[0] == pytest.approx(30.0, abs=3.0)
    assert peaks[1] == pytest.approx(90.0, abs=3.0)


def test_hook_density_scores_questions():
    events = [(5.0, "Wait, what happened?"), (6.0, "This is insane!"),
              (65.0, "And then we went home.")]
    times, scores = hook_density_score(events, 120.0)
    assert scores[0] > scores[6]  # first window has the hooks


# ------------------------------------------------------- comment spikes


def test_parse_comment_timestamps():
    assert parse_comment_timestamps(
        "loved 1:23 and the 1:02:03 part!") == [83.0, 3723.0]
    assert parse_comment_timestamps("no timestamps here") == []
    assert parse_comment_timestamps("0:45") == [45.0]
    assert parse_comment_timestamps("at 2:05:30 wow") == [7530.0]
    assert parse_comment_timestamps("") == []


def test_comment_density_points():
    texts = ["see 0:05", "0:15!!", "1:35 moment", "99:00 too far"]
    points = comment_density_points(texts, 180.0)
    assert len(points) == 18  # 180s / 10s bins
    assert points[0].value == 1.0   # 0:05
    assert points[1].value == 1.0   # 0:15
    assert points[9].value == 1.0   # 1:35
    assert points[5].value == 0.0
    # 99:00 is past the end of the video: ignored, not an error.
    assert all(p.value <= 1.0 for p in points)


def _heatmap_two_peaks():
    """Heatmap with a strong peak at 66s (1.0) and a weaker one at
    146s (0.7)."""
    points = []
    t = 0.0
    while t < 180.0:
        value = 0.1
        value = max(value, math.exp(-((t - 66) ** 2) / (2 * 3.0 ** 2)))
        value = max(value,
                    0.7 * math.exp(-((t - 146) ** 2) / (2 * 3.0 ** 2)))
        points.append(HeatPoint(t, t + 2.0, value))
        t += 2.0
    return points


def _by_peak(windows, centre):
    return next(w for w in windows if abs(w.peak_time - centre) < 5)


def test_heatmap_windows_comment_spikes_boost_ranking():
    heat = _heatmap_two_peaks()
    plain = heatmap_windows(heat, 180.0, top_n=2)
    assert _by_peak(plain, 66).score > _by_peak(plain, 146).score
    assert all(w.source == "heatmap" for w in plain)

    # Lots of timestamped comments around 2:25 flip the ranking:
    # the weaker replay peak outranks the stronger one.
    texts = ["loved 2:25!", "2:26 was insane", "2:24!!", "2:25 again"]
    points = comment_density_points(texts, 180.0)
    boosted = heatmap_windows(heat, 180.0, top_n=2, comment_points=points)
    assert _by_peak(boosted, 146).score > _by_peak(boosted, 66).score
    assert all(w.source == "heatmap+comments" for w in boosted)


def test_heatmap_windows_ignores_empty_comment_points():
    heat = _heatmap_two_peaks()
    plain = heatmap_windows(heat, 180.0, top_n=2)
    # Comments that name no moment contribute nothing: same
    # ranking, same source label as heatmap-only.
    empty = comment_density_points(["no timestamps here", "lol"], 180.0)
    assert all(p.value == 0.0 for p in empty)
    same = heatmap_windows(heat, 180.0, top_n=2, comment_points=empty)
    assert [w.score for w in same] == [w.score for w in plain]
    assert all(w.source == "heatmap" for w in same)
    assert heatmap_windows(heat, 180.0, top_n=2,
                           comment_points=None) == plain
