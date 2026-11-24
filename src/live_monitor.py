"""Live monitor: ties the chat spike detector to the ring buffer.

Watches one live stream. On a chat spike at time ``t`` it queues a
40-second clip covering ``[t-20s, t+20s]``. The second half of that
window does not exist yet at trigger time, so the clip is cut once
the buffer covers it (about 25 seconds later), in a worker thread,
while monitoring continues. One failed clip never stops the run.

Each raw cut then goes through the full pipeline (9:16 reframe plus
captions) in a second worker. Cutting and processing are separate on
purpose: processing a clip can take minutes on a CPU, and the ring
buffer only keeps 80 seconds, so the next window must be cut straight
away instead of waiting behind a slow render. If processing fails, or
the app is closing, the raw cut is kept as ``<name>-raw.mp4`` so the
footage is never lost.
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time

from .live_chat import ChatVelocity, LiveChatError, iter_live_chat
from .ring_buffer import RingBuffer, RingBufferError, resolve_stream_url

CLIP_LEN = 40.0
LEAD = 20.0
CHECK_INTERVAL_S = 0.5  # spike test at most this often, not per message
RECORDER_MAX_RESTARTS = 3  # consecutive quick failures before giving up
RECORDER_HEALTHY_S = 30.0  # a recorder that lasted this long is healthy
RECORDER_RETRY_DELAY_S = 3.0  # grows with each consecutive failure
SETTLE_S = 5.0  # wait past the window end before cutting. The segment
# holding the window's tail is still being written at t+20, and its
# packets lag the wall clock by a couple of seconds; cutting at t+22
# produced clips a second short. At t+25 the window is fully on disk.


class LiveMonitor:
    def __init__(self, url: str, out_dir: str,
                 z_threshold: float = 2.5,
                 segment_dir: str | None = None,
                 on_event=None,
                 process: bool = True,
                 model: str = "tiny",
                 caption_style: str = "hormozi",
                 process_fn=None, performance_mode: str = "auto",
                 device: str = "auto"):
        self.url = url
        self.out_dir = out_dir
        self.velocity = ChatVelocity(z_threshold=z_threshold)
        self.segment_dir = segment_dir or os.path.join(out_dir, "_buffer")
        self.buffer: RingBuffer | None = None
        self.process = process          # False: save the raw 16:9 cut only
        self.model = model              # Whisper model for captions
        self.caption_style = caption_style
        self.performance_mode = performance_mode
        self.device = device
        self._process_fn = process_fn   # tests inject a fake; default process_clip
        self._raw_dir = os.path.join(out_dir, "_raw")
        self._dry_run = False
        # GUI callback: {"type": "spike"|"clip"|"status", ...}
        self._on_event = on_event
        self._stop = threading.Event()
        self._abort = threading.Event()  # stop processing, keep raw cuts
        self._recorder_started = 0.0
        self._recorder_failures = 0
        self._pending: list[tuple[float, float, str]] = []
        self._pending_lock = threading.Lock()
        self._to_process: queue.Queue = queue.Queue()
        self.clips_saved: list[str] = []
        self.spikes_seen = 0

    def stop(self, abort_processing: bool = False) -> None:
        """Stop monitoring. Queued clips still finish processing unless
        ``abort_processing`` is set, in which case their raw cuts are kept."""
        if abort_processing:
            self._abort.set()
        self._stop.set()

    def _emit(self, event: dict) -> None:
        if self._on_event is not None:
            self._on_event(event)

    def _chat_loop(self, chat_iter) -> None:
        # Every message is recorded, but the spike test (which scans the
        # whole baseline) runs on a timer. Running it per message cost
        # milliseconds each and made a 100+ msg/s chat fall behind.
        last_check = 0.0
        try:
            for _message in chat_iter:
                if self._stop.is_set():
                    break
                now = time.time()
                self.velocity.feed(now)
                if now - last_check < CHECK_INTERVAL_S:
                    continue
                last_check = now
                triggered, z, count = self.velocity.check(now)
                if triggered:
                    self._on_spike(now, z, count)
        except LiveChatError as exc:
            print(f"Chat source ended or failed: {exc}")
            self._emit({"type": "status",
                        "text": f"Live chat stopped: {exc}. No more spikes "
                                f"will be detected."})
        else:
            if not self._stop.is_set():
                self._emit({"type": "status",
                            "text": "Live chat ended. No more spikes will "
                                    "be detected."})

    def _on_spike(self, now: float, z: float, count: int) -> None:
        self.spikes_seen += 1
        print(f"SPIKE at {time.strftime('%H:%M:%S')}  "
              f"z={z:.1f}  {count} msgs/10s")
        self._emit({"type": "spike", "z": z, "count": count,
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

    def _finish(self, path: str) -> None:
        self.clips_saved.append(path)
        print(f"  saved {path}")
        self._emit({"type": "clip", "path": path})

    def _clip_worker(self) -> None:
        """Cut each queued window out of the ring buffer as soon as it
        is fully buffered."""
        while not self._stop.is_set() or self._pending:
            with self._pending_lock:
                now = time.time()
                due, self._pending = (
                    [p for p in self._pending if p[1] + SETTLE_S <= now],
                    [p for p in self._pending if p[1] + SETTLE_S > now],
                )
            for start, end, out_path in due:
                if self.buffer is None:
                    continue
                try:
                    if self.process:
                        os.makedirs(self._raw_dir, exist_ok=True)
                        raw = os.path.join(self._raw_dir,
                                           os.path.basename(out_path))
                        self.buffer.extract_clip(start, end, raw)
                        self._to_process.put((raw, out_path))
                        self._emit({"type": "status", "text":
                                    f"Cut {os.path.basename(out_path)}, "
                                    f"queued for reframe and captions"})
                    else:
                        self.buffer.extract_clip(start, end, out_path)
                        self._finish(out_path)
                except Exception as exc:
                    # Any failure (not only RingBufferError): an uncaught
                    # error here used to kill this thread and silently end
                    # all later clips.
                    print(f"  clip failed (buffer too short?): {exc}")
                    self._emit({"type": "status",
                                "text": f"Clip failed: {exc}"})
            time.sleep(1.0)

    def _run_process(self, raw: str, out_path: str) -> None:
        fn = self._process_fn
        if fn is None:
            from .pipeline import process_clip as fn
        fn(raw, out_path, model=self.model, caption_style=self.caption_style,
           log=print, performance_mode=self.performance_mode,
           device=self.device,
           progress_cb=lambda frac, label: self._emit(
               {"type": "progress", "pct": int(round(frac * 100)),
                "label": label}))

    def _keep_raw(self, raw: str, out_path: str, why: str) -> None:
        kept = out_path[:-4] + "-raw.mp4" if out_path.endswith(".mp4") else out_path + "-raw"
        try:
            shutil.move(raw, kept)
            print(f"  {why}; raw cut kept as {kept}")
            self._emit({"type": "status", "text": f"{why}; raw cut kept: {kept}"})
        except OSError as exc:
            print(f"  could not keep raw cut {raw}: {exc}")

    def _process_worker(self) -> None:
        """Reframe and caption queued cuts, one at a time."""
        while True:
            item = self._to_process.get()
            if item is None:
                return
            raw, out_path = item
            name = os.path.basename(out_path)
            if self._abort.is_set():
                self._keep_raw(raw, out_path, "stopped before processing")
                continue
            self._emit({"type": "status",
                        "text": f"Reframing and captioning {name} ..."})
            try:
                self._run_process(raw, out_path)
            except Exception as exc:
                self._keep_raw(raw, out_path, f"processing failed ({exc})")
                continue
            try:
                os.remove(raw)
            except OSError:
                pass
            self._finish(out_path)

    def _start_workers(self):
        clip_thread = threading.Thread(target=self._clip_worker, daemon=True)
        clip_thread.start()
        proc_thread = None
        if self.process:
            proc_thread = threading.Thread(target=self._process_worker,
                                           daemon=True)
            proc_thread.start()
        return clip_thread, proc_thread

    def _finish_processing(self, proc_thread) -> None:
        if proc_thread is not None:
            self._to_process.put(None)  # sentinel: exit after the queue drains
            proc_thread.join()
        if self.process:
            try:
                os.rmdir(self._raw_dir)  # only succeeds when empty
            except OSError:
                pass

    def _restart_recorder(self, stream_source: str | None) -> bool:
        """The ffmpeg recorder died (network drop, stream ended, expired
        URL). Try to resume it. Returns False once it should give up."""
        old = self.buffer
        code = getattr(old, "exit_code", None)
        if time.time() - self._recorder_started >= RECORDER_HEALTHY_S:
            self._recorder_failures = 0
        self._recorder_failures += 1
        if self._recorder_failures > RECORDER_MAX_RESTARTS:
            self._emit({"type": "status",
                        "text": "Stream recording stopped and could not be "
                                "restarted (the stream may have ended). "
                                "Stopping."})
            return False
        # The recorder's stderr tail names the real failure (a bare
        # exit code says nothing: on Windows the recorder once died
        # with 4294967295 and no reason at all).
        detail = ""
        if old is not None:
            tail = old.last_stderr()
            if tail:
                detail = f" Recorder said: {tail[-500:]}"
        self._emit({"type": "status",
                    "text": f"Stream recording stopped (ffmpeg exit {code}); "
                            f"reconnecting "
                            f"({self._recorder_failures}/{RECORDER_MAX_RESTARTS}) ...{detail}"})
        if old is not None:
            old.stop()
        if self._stop.wait(RECORDER_RETRY_DELAY_S * self._recorder_failures):
            return True
        try:
            source = stream_source or resolve_stream_url(self.url)
            self.buffer = RingBuffer(source, self.segment_dir)
            self.buffer.start()
            self._recorder_started = time.time()
        except Exception as exc:
            self._emit({"type": "status",
                        "text": f"Could not reconnect to the stream: {exc}"})
        return True

    def run(self, duration_s: float | None = None,
            dry_run: bool = False,
            chat_iter=None, stream_source: str | None = None) -> list[str]:
        """Monitor until ``duration_s`` elapses (or forever when None).

        ``chat_iter`` and ``stream_source`` exist for tests: a scripted
        chat feed and a local file standing in for the live stream.
        Returns the list of saved clip paths. After monitoring stops this
        waits for queued clips to finish processing.
        """
        os.makedirs(self.out_dir, exist_ok=True)
        self._dry_run = dry_run
        source = stream_source or resolve_stream_url(self.url)
        self.buffer = RingBuffer(source, self.segment_dir)
        self.buffer.start()
        self._recorder_started = time.time()
        if chat_iter is None:
            chat_iter = iter_live_chat(self.url)
        chat_thread = threading.Thread(target=self._chat_loop, args=(chat_iter,),
                                       daemon=True)
        clip_thread, proc_thread = self._start_workers()
        chat_thread.start()
        started = time.time()
        try:
            while not self._stop.is_set():
                if duration_s is not None and time.time() - started >= duration_s:
                    break
                if (self.buffer is not None
                        and hasattr(self.buffer, "is_running")
                        and not self.buffer.is_running()):
                    if not self._restart_recorder(stream_source):
                        break
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Stopped by user.")
        finally:
            self._stop.set()
            chat_thread.join(timeout=5)
            # Let queued windows be cut while their footage is buffered.
            clip_thread.join(timeout=30)
            if self.buffer is not None:
                self.buffer.stop()
            # Nothing from the stream is kept once monitoring ends.
            shutil.rmtree(self.segment_dir, ignore_errors=True)
            if proc_thread is not None and not self._abort.is_set():
                waiting = self._to_process.qsize()
                if waiting:
                    print(f"Finishing {waiting} queued clip(s) ...")
            self._finish_processing(proc_thread)
        return self.clips_saved
