"""Ingestion tests. The live probe hits the network."""

import json
import subprocess

from src.ingestion import download_section, probe

RICK_ASTLEY = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_probe_real_vod_has_heatmap():
    info = probe(RICK_ASTLEY)
    assert info.is_live is False
    assert info.duration == 213
    assert info.has_heatmap
    assert len(info.heatmap) == 100
    first = info.heatmap[0]
    assert first.start_time == 0.0
    assert 0.0 <= first.value <= 1.0


def _probe_streams(path: str) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,codec_name", "-show_entries", "format=duration",
        "-of", "json", path], text=True)
    return json.loads(out)


def test_download_section_cuts_exact_window(tmp_path):
    """Regression test: the section must actually be cut. An early
    version passed the CLI's "--download-sections" strings to the
    Python API, which silently ignored them and downloaded the
    whole 213s video."""
    out = str(tmp_path / "section.mp4")
    download_section(RICK_ASTLEY, 64, 69, out)
    data = _probe_streams(out)
    duration = float(data["format"]["duration"])
    assert 4.5 <= duration <= 5.5, f"duration {duration}, expected ~5s"
    kinds = {s["codec_type"] for s in data["streams"]}
    assert kinds == {"video", "audio"}
