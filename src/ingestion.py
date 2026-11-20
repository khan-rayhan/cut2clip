"""Ingestion: probe a URL with yt-dlp and return structured metadata.

Uses the yt_dlp Python API (no subprocess, no binary path juggling).
Verified 2026-11-18 against a real YouTube pre-recorded video: the info dict carries
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


def fetch_comments(url: str, max_comments: int = 100) -> list[dict]:
    """Fetch up to *max_comments* comments with yt-dlp (no API key).

    Returns the raw comment dicts (each has at least ``text``).
    Raises IngestionError when comments are disabled or unavailable;
    callers fall back to the other highlight signals. The cap is
    enforced two ways: yt-dlp's ``max_comments`` extractor argument
    (``youtube:max_comments``) stops the pagination, and the result
    is truncated again here in case the extractor ignores it.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "getcomments": True,
        "extractor_args": {"youtube": {"max_comments": [str(max_comments)]}},
    }
    try:
        info = _extract(url, opts, download=False)
    except Exception as exc:
        raise IngestionError(f"Could not fetch comments for {url!r}: {exc}") from exc
    if not isinstance(info, dict):
        raise IngestionError(f"Could not fetch comments for {url!r}: empty result")
    comments = info.get("comments") or []
    return [c for c in comments if isinstance(c, dict)][:max_comments]


def fetch_comment_points(url: str, duration: float):
    """Best-effort comment-density signal for a URL.

    Returns (points, comment count); (None, 0) when comments are
    disabled or unavailable, so the caller falls back to the
    heatmap alone. (The highlights import is lazy: highlights
    imports this module, so a top-level import would be circular.)"""
    from .highlights import comment_density_points

    try:
        comments = fetch_comments(url)
    except Exception:
        return None, 0
    texts = [c.get("text") or "" for c in comments]
    points = comment_density_points(texts, duration)
    if not any(p.value > 0 for p in points):
        return None, len(comments)  # comments exist but name no moment
    return points, len(comments)


def audio_stream_source(url: str) -> tuple[str, dict]:
    """Direct audio URL plus the HTTP headers it needs, without
    downloading anything. ffmpeg reads it as a stream and the audio
    never touches the disk (see highlights.audio_energy_series)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "bestaudio/best",
        "noplaylist": True,
    }
    try:
        info = _extract(url, opts, download=False)
    except Exception as exc:
        raise IngestionError(f"Could not open audio for {url!r}: {exc}") from exc
    media_url = info.get("url") if isinstance(info, dict) else None
    if not media_url:
        raise IngestionError(f"No streamable audio URL for {url!r}")
    return media_url, dict(info.get("http_headers") or {})


# A section download longer than the request by more than this means the
# format could not be cut, so the whole video came down. Treated as a failure.
MAX_OVERSHOOT_S = 10.0


def _media_duration(path: str) -> float | None:
    """Duration in seconds via ffprobe, or None when it cannot be read."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True).stdout.strip()
        return float(out) if out else None
    except (OSError, ValueError):
        return None


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
    # 1080p, H.264 preferred, with a fallback chain: the generic
    # "bv*+ba/b" picks VP9 webm video, whose download stalls on
    # some proxies, and an uncapped "bv*[ext=mp4]" picks the 229 MB
    # 4K AV1 file. Preferring avc1 (H.264) keeps the merge clean,
    # and a 40-second 1080p section is only about 30-60 MB, so
    # the download size is not a concern.
    #
    # Audio MUST be ba[ext=m4a]: plain "ba" picks Opus/Vorbis,
    # which cannot go into an MP4, so yt-dlp switches the output
    # to MKV ("section.mp4.mkv") and the expected file never
    # appears. The last fallback is mp4-only for the same reason.
    #
    # NOTE: the section is passed as a "download_ranges" CALLBACK,
    # not as the CLI's "--download-sections" strings. The Python
    # API wants (info_dict, ydl) -> [{"start_time", "end_time"}].
    # Passing the CLI string form (or a "download_sections" key)
    # is silently ignored and downloads the whole video.
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba[ext=m4a]/b[height<=1080][ext=mp4]",
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
    got = _media_duration(out_path)
    if got is not None and got > (end - start) + MAX_OVERSHOOT_S:
        os.remove(out_path)  # never leave a full-length video on disk
        raise IngestionError(
            f"Asked for {end - start:.0f}s but got {got:.0f}s, so the whole "
            f"video was downloaded. The file was deleted.")
    return out_path
