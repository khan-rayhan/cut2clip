"""Live chat velocity monitoring for Mode B.

Velocity is computed on message *arrival* time, never on the source
timestamp field, so the same code works for YouTube, Twitch, and any
other chat source.

Trigger rule: the message rate in the last ``window_s`` seconds beats
the rolling baseline (mean and standard deviation of per-second rates
over ``baseline_s``) by more than ``z_threshold`` standard deviations,
with at least ``min_messages`` in the window and at least
``min_baseline_s`` of history. A cooldown follows every trigger.
"""

from __future__ import annotations

import collections
import math
import statistics
import threading
import time


class LiveChatError(Exception):
    """Raised when a live chat source cannot be opened."""


class ChatVelocity:
    def __init__(self, window_s: float = 10.0, baseline_s: float = 300.0,
                 z_threshold: float = 2.5, min_messages: int = 10,
                 min_baseline_s: float = 60.0, cooldown_s: float = 45.0):
        self.window_s = window_s
        self.baseline_s = baseline_s
        self.z_threshold = z_threshold
        self.min_messages = min_messages
        self.min_baseline_s = min_baseline_s
        self.cooldown_s = cooldown_s
        self._arrivals: collections.deque[float] = collections.deque()
        self._last_trigger: float | None = None
        self._lock = threading.Lock()

    def feed(self, ts: float | None = None) -> None:
        """Record one message arriving at ``ts`` (default: now)."""
        ts = time.time() if ts is None else ts
        with self._lock:
            self._arrivals.append(ts)
            cutoff = ts - self.baseline_s - self.window_s
            while self._arrivals and self._arrivals[0] < cutoff:
                self._arrivals.popleft()

    def zscore(self, now: float | None = None) -> tuple[float, int, float]:
        """Return (z, messages in current window, current rate per sec).

        z is 0 when there is not enough baseline yet.
        """
        now = time.time() if now is None else now
        with self._lock:
            window_count = sum(1 for ts in self._arrivals
                               if now - self.window_s <= ts <= now)
            history = list(self._arrivals)
        if not history:
            return 0.0, 0, 0.0
        # The baseline covers only seconds that actually have history.
        # Counting the time before the first message as zeros dragged
        # the mean down and fired a false spike ten seconds into a
        # perfectly flat chat.
        baseline_end = now - self.window_s
        baseline_start = max(history[0], baseline_end - self.baseline_s)
        span = baseline_end - baseline_start
        if span < self.min_baseline_s:
            return 0.0, window_count, window_count / self.window_s
        counts: dict[int, int] = collections.Counter()
        for ts in history:
            if baseline_start <= ts < baseline_end:
                counts[int(ts - baseline_start)] += 1
        per_sec = [counts.get(i, 0) for i in range(int(span))]
        mean = statistics.fmean(per_sec)
        std = statistics.pstdev(per_sec)
        rate = window_count / self.window_s
        if std < 1e-9:
            z = 0.0 if rate <= mean else float("inf")
        else:
            z = (rate - mean) / std
        return z, window_count, rate

    def check(self, now: float | None = None) -> tuple[bool, float, int]:
        """Return (triggered, z, window message count)."""
        now = time.time() if now is None else now
        if self._last_trigger is not None and now - self._last_trigger < self.cooldown_s:
            z, count, _ = self.zscore(now)
            return False, z, count
        oldest = self._arrivals[0] if self._arrivals else now
        if now - oldest < self.min_baseline_s:
            return False, 0.0, 0
        z, count, _ = self.zscore(now)
        if z > self.z_threshold and count >= self.min_messages:
            self._last_trigger = now
            return True, z, count
        return False, z, count


def iter_live_chat(url: str):
    """Yield chat message dicts from a live stream as they arrive.

    Uses chat-downloader. Raises LiveChatError when the source cannot
    be opened. The caller uses arrival time for velocity, so the
    message payload is passed through untouched.
    """
    try:
        from chat_downloader import ChatDownloader
    except ImportError as exc:
        raise LiveChatError(f"chat-downloader is not installed: {exc}") from exc
    try:
        downloader = ChatDownloader()
        chat = downloader.get_chat(url)
        for message in chat:
            yield message
    except Exception as exc:
        raise LiveChatError(f"Could not open live chat for {url!r}: {exc}") from exc
