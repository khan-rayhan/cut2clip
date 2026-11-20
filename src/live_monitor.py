"""Live monitor: ties the chat spike detector to the ring buffer.

Watches one live stream. On a chat spike at time ``t`` it queues a
40-second clip covering ``[t-20s, t+20s]``. The second half of that
window does not exist yet at trigger time, so the clip is cut once
the buffer covers it (about 22 seconds later), in a worker thread,
while monitoring continues. One failed clip never stops the run.
"""

from __future__ import annotations

import os
import threading
import time

from .live_chat import ChatVelocity, LiveChatError, iter_live_chat
from .ring_buffer import RingBuffer, RingBufferError, resolve_stream_url

CLIP_LEN = 40.0
LEAD = 20.0
SETTLE_S = 5.0  # wait past the window end before cutting. The segment
# holding the window's tail is still being written at t+20, and its
# packets lag the wall clock by a couple of seconds; cutting at t+22
# produced clips a second short. At t+25 the window is fully on disk.


class LiveMonitor:
    def __init__(self, url: str, out_dir: str,
                 z_threshold: float = 2.5,
                 segment_dir: str | None = None,
                 on_event=None):
        self.url = url
        self.out_dir = out_dir
        self.velocity = ChatVelocity(z_threshold=z_threshold)
        self.segment_dir = segment_dir or os.path.join(out_dir, "_buffer")
        self.buffer: RingBuffer | None = None
        self._dry_run = False
        self._on_event = on_event  # GUI callback: {"type": "spike"|"clip", ...}
        self._stop = threading.Event()
        self._pending: list[tuple[float, float, str]] = []
        self._pending_lock = threading.Lock()
        self.clips_saved: list[str] = []
        self.spikes_seen = 0

    def _chat_loop(self, chat_iter) -> None:
        try:
            for _message in chat_iter:
                if self._stop.is_set():
                    break
                now = time.time()
                self.velocity.feed(now)
                triggered, z, count = self.velocity.check(now)
                if triggered:
                    self._on_spike(now, z, count)
        except LiveChatError as exc:
            print(f"Chat source ended or failed: {exc}")

    def _on_spike(self, now: float, z: float, count: int) -> None:
        self.spikes_seen += 1
        print(f"SPIKE at {time.strftime('%H:%M:%S')}  "
              f"z={z:.1f}  {count} msgs/10s")
        if self._on_event is not None:
            self._on_event({"type": "spike", "z": z, "count": count,
                            "time": time.strftime("%H:%M:%S")})
        if self._dry_run:
            return
        start = now - LEAD
        end = now + (CLIP_LEN - LEAD)
        stamp = time.strftime("%Hh%Mm%Ss", time.localtime(now))
        out_path = os.path.join(
            self.out_dir, f"live-{stamp}_{count}msgs.mp4")
        with self._pending_lock:
            self._pending.append((start, end, out_path))
        print(f"  clip queued: {out_path}")

    def _clip_worker(self) -> None:
        while not self._stop.is_set() or self._pending:
            due: list[tuple[float, float, str]] = []
            with self._pending_lock:
                now = time.time()
                ready, self._pending = (
                    [p for p in self._pending if p[1] + SETTLE_S <= now],
                    [p for p in self._pending if p[1] + SETTLE_S > now],
                )
                due = ready
            for start, end, out_path in due:
                if self.buffer is None:
                    continue
                try:
                    self.buffer.extract_clip(start, end, out_path)
                    self.clips_saved.append(out_path)
                    print(f"  saved {out_path}")
                    if self._on_event is not None:
                        self._on_event({"type": "clip", "path": out_path})
                except RingBufferError as exc:
                    print(f"  clip failed (buffer too short?): {exc}")
            time.sleep(1.0)

    def run(self, duration_s: float | None = None,
            dry_run: bool = False,
            chat_iter=None, stream_source: str | None = None) -> list[str]:
        """Monitor until ``duration_s`` elapses (or forever when None).

        ``chat_iter`` and ``stream_source`` exist for tests: a scripted
        chat feed and a local file standing in for the live stream.
        Returns the list of saved clip paths.
        """
        os.makedirs(self.out_dir, exist_ok=True)
        self._dry_run = dry_run
        source = stream_source or resolve_stream_url(self.url)
        self.buffer = RingBuffer(source, self.segment_dir)
        self.buffer.start()
        if chat_iter is None:
            chat_iter = iter_live_chat(self.url)
        chat_thread = threading.Thread(target=self._chat_loop, args=(chat_iter,),
                                       daemon=True)
        clip_thread = threading.Thread(target=self._clip_worker, daemon=True)
        chat_thread.start()
        clip_thread.start()
        started = time.time()
        try:
            while not self._stop.is_set():
                if duration_s is not None and time.time() - started >= duration_s:
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Stopped by user.")
        finally:
            self._stop.set()
            chat_thread.join(timeout=5)
            # Let queued clips finish if their window is buffered.
            clip_thread.join(timeout=30)
            if self.buffer is not None:
                self.buffer.stop()
        return self.clips_saved
