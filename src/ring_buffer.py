"""Rolling ring buffer for Mode B (live).

ffmpeg writes 10-second stream-copy segments into a folder while a
pruner thread deletes anything older than the retention window, so
the last 80 seconds of the stream are always on disk. Segment files
are named by wall-clock start time, which is the same clock the chat
spike detector uses, so a spike at time ``t`` maps directly onto the
segments covering ``[t-20s, t+20s]``.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import threading
import time

SEGMENT_TIME = 10
KEEP_SEGMENTS = 8  # 8 x 10s = 80s retained, above the 60s minimum


class RingBufferError(Exception):
    """Raised when the buffer cannot start or a clip cannot be cut."""


def resolve_stream_url(url: str) -> str:
    """Return a playable HLS URL for *url*.

    A direct .m3u8 URL is returned as-is. Anything else goes through
    streamlink, which resolves YouTube and Twitch (and others) to
    their underlying stream URL.
    """
    if url.endswith(".m3u8"):
        return url
    try:
        from streamlink import Streamlink
    except ImportError as exc:
        raise RingBufferError(f"streamlink is not installed: {exc}") from exc
    try:
        session = Streamlink()
        streams = session.streams(url)
    except Exception as exc:
        raise RingBufferError(f"Could not resolve stream {url!r}: {exc}") from exc
    for quality in ("best", "1080p", "720p", "480p", "worst"):
        stream = streams.get(quality)
        if stream is not None:
            return stream.url
    raise RingBufferError(f"No playable stream found for {url!r}")


_SEGMENT_RE = re.compile(r"seg-(\d{8}T\d{6})\.ts")


def _parse_segment_time(name: str) -> float | None:
    match = _SEGMENT_RE.match(name)
    if not match:
        return None
    # ffmpeg writes segment names in LOCAL time, so parse them as local
    # time too. Parsing them as UTC put every segment six hours in the
    # future on a +06:00 machine and made every clip "older than the
    # buffer".
    dt = datetime.datetime.strptime(match.group(1), "%Y%m%dT%H%M%S")
    return time.mktime(dt.timetuple())


class RingBuffer:
    """Records a live source into timestamped segments, pruned to a
    rolling window. ``source`` is an HLS URL or a local file path
    (local files are read with ``-re`` so they behave like a live
    stream)."""

    def __init__(self, source: str, segment_dir: str,
                 segment_time: int = SEGMENT_TIME,
                 keep_segments: int = KEEP_SEGMENTS):
        self.source = source
        self.segment_dir = segment_dir
        self.segment_time = segment_time
        self.keep_seconds = keep_segments * segment_time
        self._proc: subprocess.Popen | None = None
        self._pruner: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        os.makedirs(self.segment_dir, exist_ok=True)
        cmd = ["ffmpeg", "-v", "error"]
        if os.path.exists(self.source):
            cmd += ["-re"]  # local file: read at real-time speed
        cmd += [
            "-i", self.source,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.segment_time),
            "-strftime", "1",
            os.path.join(self.segment_dir, "seg-%Y%m%dT%H%M%S.ts"),
        ]
        try:
            self._proc = subprocess.Popen(cmd)
        except FileNotFoundError as exc:
            raise RingBufferError(f"ffmpeg is not installed: {exc}") from exc
        self._stop.clear()
        self._pruner = threading.Thread(target=self._prune_loop, daemon=True)
        self._pruner.start()

    def _segments(self) -> list[tuple[float, str]]:
        """(wall-clock start, path) for every segment on disk, oldest first."""
        found = []
        for name in os.listdir(self.segment_dir):
            ts = _parse_segment_time(name)
            if ts is not None:
                found.append((ts, os.path.join(self.segment_dir, name)))
        found.sort()
        return found

    def _prune_loop(self) -> None:
        while not self._stop.wait(2.0):
            cutoff = time.time() - self.keep_seconds
            for ts, path in self._segments():
                if ts < cutoff:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def available_range(self) -> tuple[float | None, float | None]:
        """(earliest segment start, latest segment end) or (None, None)."""
        segments = self._segments()
        if not segments:
            return None, None
        return segments[0][0], segments[-1][0] + self.segment_time

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._pruner is not None:
            self._pruner.join(timeout=5)

    def extract_clip(self, start_ts: float, end_ts: float,
                     out_path: str) -> str:
        """Cut ``[start_ts, end_ts]`` out of the buffered segments.

        One extra segment is included on each side so the cut can land
        exactly on the requested times. The clip is re-encoded to
        H.264/AAC so the boundaries are frame accurate.
        """
        segments = self._segments()
        if not segments:
            raise RingBufferError("Ring buffer is empty, nothing to cut.")
        earliest = segments[0][0]
        if end_ts <= earliest:
            raise RingBufferError("Requested window is older than the buffer.")
        start_ts = max(start_ts, earliest)
        chosen = [(ts, p) for ts, p in segments
                  if ts + self.segment_time > start_ts - self.segment_time
                  and ts < end_ts + self.segment_time]
        if not chosen:
            raise RingBufferError("No buffered segments cover the window.")
        first_start = chosen[0][0]
        offset = max(0.0, start_ts - first_start)
        duration = end_ts - start_ts
        list_path = os.path.join(self.segment_dir, "concat.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            for _, path in chosen:
                f.write(f"file '{path}'\n")
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-ss", f"{offset:.3f}", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RingBufferError(f"ffmpeg clip cut failed: {result.stderr[-300:]}")
        return out_path
