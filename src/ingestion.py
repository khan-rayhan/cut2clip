"""Ingestion: probe a URL with yt-dlp and return structured metadata.

Uses the yt_dlp Python API (no subprocess, no binary path juggling).
Verified 2026-11-18 against a real YouTube VOD: the info dict carries
``heatmap`` as a list of ``{"start_time", "end_time", "value"}`` with
value normalised 0..1, plus ``is_live`` and ``duration``.
"""

from __future__ import annotations

import dataclasses
import os

import yt_dlp


class IngestionError(Exception):
    """Raised when a URL cannot be probed (bad link, private, removed)."""


@dataclasses.dataclass
class HeatPoint:
    start_time: float
    end_time: float
    value: float


@dataclasses.dataclass
class VideoInfo:
    url: str
    title: str | None
    duration: float | None  # seconds; None for an open-ended live stream
    is_live: bool
    heatmap: list[HeatPoint]
    # subtitle track urls by language code, e.g. {"en": "https://...json3"}
    auto_caption_urls: dict[str, str]

    @property
    def has_heatmap(self) -> bool:
        return len(self.heatmap) > 0


def _parse_heatmap(raw) -> list[HeatPoint]:
    points: list[HeatPoint] = []
    if not isinstance(raw, list):
        return points
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            points.append(
                HeatPoint(
                    start_time=float(entry["start_time"]),
                    end_time=float(entry["end_time"]),
                    value=float(entry["value"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    points.sort(key=lambda p: p.start_time)
    return points


def _caption_urls(info: dict) -> dict[str, str]:
    """Prefer automatic captions in json3 form (has word timings)."""
    urls: dict[str, str] = {}
    for key in ("automatic_captions", "subtitles"):
        tracks = info.get(key) or {}
        for lang, formats in tracks.items():
            if lang in urls:
                continue
            for fmt in formats or []:
                if fmt.get("ext") == "json3" and fmt.get("url"):
                    urls[lang] = fmt["url"]
                    break
    return urls


def _extract(url: str, opts: dict, download: bool):
    """Run yt-dlp once. On a certificate error (common behind MITM
    proxies whose CA is not in certifi's bundle) retry once with
    certificate checks off and warn, instead of failing outright."""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=download)
    except Exception as exc:
        msg = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "certificate verify failed" in msg:
            import sys
            print("WARNING: certificate check failed (proxy network?) - "
                  "retrying with certificate verification off.",
                  file=sys.stderr)
            opts = {**opts, "nocheckcertificate": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        raise


def probe(url: str) -> VideoInfo:
    """Probe *url* without downloading. Raises IngestionError on failure."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        info = _extract(url, opts, download=False)
    except Exception as exc:  # yt-dlp raises DownloadError and friends
        raise IngestionError(f"Could not probe URL {url!r}: {exc}") from exc
    if not isinstance(info, dict):
        raise IngestionError(f"Could not probe URL {url!r}: empty result")
    duration = info.get("duration")
    return VideoInfo(
        url=info.get("webpage_url") or url,
        title=info.get("title"),
        duration=float(duration) if duration is not None else None,
        is_live=bool(info.get("is_live")),
        heatmap=_parse_heatmap(info.get("heatmap")),
        auto_caption_urls=_caption_urls(info),
    )


def download_audio(url: str, out_path: str) -> str:
    """Download best audio only to *out_path*. Returns the path."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": out_path,
        "noplaylist": True,
    }
    try:
        _extract(url, opts, download=True)
    except Exception as exc:
        raise IngestionError(f"Could not download audio for {url!r}: {exc}") from exc
    return out_path


def _fmt_clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def download_section(url: str, start: float, end: float,
                     out_path: str) -> str:
    """Download the ``[start, end]`` seconds of a video, video and
    audio merged into one MP4. Used by the GUI to fetch one highlight
    window before processing it."""
    # MP4-only, 720p-capped formats on purpose: the generic
    # "bv*+ba/b" picks VP9 webm video, whose download stalls on
    # some proxies, and an uncapped "bv*[ext=mp4]" picks the 229 MB
    # 4K AV1 file. 720p H.264 MP4 merges cleanly and is plenty for
    # a 1080x1920 vertical crop.
    #
    # NOTE: the section is passed as a "download_ranges" CALLBACK,
    # not as the CLI's "--download-sections" strings. The Python
    # API wants (info_dict, ydl) -> [{"start_time", "end_time"}].
    # Passing the CLI string form (or a "download_sections" key)
    # is silently ignored and downloads the whole video.
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]",
        "outtmpl": out_path,
        "noplaylist": True,
        "download_ranges": lambda info_dict, ydl: [
            {"start_time": start, "end_time": end}],
        "force_keyframes_at_cuts": True,
    }
    try:
        _extract(url, opts, download=True)
    except Exception as exc:
        raise IngestionError(
            f"Could not download {start:.0f}-{end:.0f}s of {url!r}: {exc}"
        ) from exc
    if not os.path.exists(out_path):
        raise IngestionError(f"Download finished but {out_path!r} is missing.")
    return out_path
