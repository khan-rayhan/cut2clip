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


# ---------------------------------------------------------------- storage guards

import os
import subprocess

import pytest

from src import ingestion


def _fake_extract_writing(seconds):
    """Stand-in for yt-dlp that writes a ``seconds``-long file."""
    def fake(url, opts, download):
        out = opts["outtmpl"]
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"color=c=black:size=64x64:rate=1:duration={seconds}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "mp4", out],
            check=True)
        return {}
    return fake


def test_download_section_rejects_a_full_length_download(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion, "_extract", _fake_extract_writing(120))
    out = str(tmp_path / "clip.mp4")
    with pytest.raises(ingestion.IngestionError, match="whole"):
        ingestion.download_section("u", 10, 50, out)
    assert not os.path.exists(out)  # the long file is deleted


def test_download_section_accepts_the_requested_length(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion, "_extract", _fake_extract_writing(40))
    out = str(tmp_path / "clip.mp4")
    assert ingestion.download_section("u", 10, 50, out) == out
    assert os.path.exists(out)


def test_audio_stream_source_returns_url_without_downloading(monkeypatch):
    seen = {}

    def fake(url, opts, download):
        seen["download"] = download
        return {"url": "https://cdn.example/a.m4a",
                "http_headers": {"User-Agent": "x"}}

    monkeypatch.setattr(ingestion, "_extract", fake)
    assert ingestion.audio_stream_source("u") == (
        "https://cdn.example/a.m4a", {"User-Agent": "x"})
    assert seen["download"] is False
    assert not hasattr(ingestion, "download_audio")  # the save-to-disk path is gone
