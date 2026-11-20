"""Monitor test: scripted chat burst plus a local file as the stream.

Runs in real time for about 45 seconds: 15 seconds of flat chat,
a burst, then the queued 40-second clip is cut once its window is
fully buffered.
"""

import subprocess
import time

from src.live_chat import ChatVelocity
from src.live_monitor import LiveMonitor


def _make_test_video(path, duration=120):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=30:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", path],
        check=True)


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def _scripted_chat():
    """Flat chat for 30s, then an 80-message burst over 5s.

    The burst lands about 30s in, so the [t-20s, t+20s] clip window
    is fully inside the buffer.
    """
    start = time.time()
    for _ in range(60):  # 2 per second for 30 seconds
        yield {"text": "hi"}
        time.sleep(0.5)
    for _ in range(80):
        yield {"text": "WOW clip it"}
        time.sleep(0.06)
    while time.time() - start < 60:
        yield {"text": "hi"}
        time.sleep(0.5)


def test_monitor_saves_clip_on_burst(tmp_path):
    src = tmp_path / "src.mp4"
    _make_test_video(str(src))
    out_dir = tmp_path / "clips"
    monitor = LiveMonitor("https://example.invalid/live", str(out_dir),
                          process=False)  # this test checks the raw cut
    # Short baseline so the test does not need 60s of history.
    monitor.velocity = ChatVelocity(min_baseline_s=10, baseline_s=60)
    saved = monitor.run(duration_s=60, chat_iter=_scripted_chat(),
                        stream_source=str(src))
    assert monitor.spikes_seen == 1
    assert len(saved) == 1
    assert abs(_duration(saved[0]) - 40.0) < 0.6


# ---------------------------------------------------------------- processing

import os
import shutil


class _FakeBuffer:
    def extract_clip(self, start, end, out_path):
        with open(out_path, "wb") as fh:
            fh.write(b"raw-cut")
        return out_path

    def stop(self):
        pass


def _run_workers_once(monitor, out_path):
    """Queue one already-due window and drain both workers."""
    os.makedirs(monitor.out_dir, exist_ok=True)
    monitor.buffer = _FakeBuffer()
    monitor._pending.append((time.time() - 100, time.time() - 60, out_path))
    clip_thread, proc_thread = monitor._start_workers()
    monitor._stop.set()
    clip_thread.join(timeout=10)
    monitor._finish_processing(proc_thread)


def test_live_clip_goes_through_processing(tmp_path):
    """The saved clip is the processed one, not the raw 16:9 cut."""
    out_dir = tmp_path / "clips"
    out_path = str(out_dir / "live-x.mp4")
    calls = []

    def fake_process(raw, out, model, log, caption_style="hormozi",
                     performance_mode="auto", device="auto"):
        calls.append((raw, out, model, caption_style))
        assert os.path.exists(raw)
        with open(out, "wb") as fh:
            fh.write(b"processed")

    events = []
    monitor = LiveMonitor("u", str(out_dir), model="base",
                          caption_style="tiktok",
                          process_fn=fake_process, on_event=events.append)
    _run_workers_once(monitor, out_path)

    assert monitor.clips_saved == [out_path]
    assert open(out_path, "rb").read() == b"processed"
    assert calls and calls[0][1] == out_path and calls[0][2] == "base"
    assert calls[0][3] == "tiktok"  # caption style reaches process_clip
    assert not os.path.exists(calls[0][0])        # raw cut cleaned up
    assert not os.path.exists(monitor._raw_dir)   # and its folder
    assert any(e["type"] == "clip" and e["path"] == out_path for e in events)


def test_failed_processing_keeps_the_raw_cut(tmp_path):
    out_dir = tmp_path / "clips"
    out_path = str(out_dir / "live-y.mp4")

    def boom(raw, out, model, log, caption_style="hormozi"):
        raise RuntimeError("whisper exploded")

    monitor = LiveMonitor("u", str(out_dir), process_fn=boom)
    _run_workers_once(monitor, out_path)

    kept = str(out_dir / "live-y-raw.mp4")
    assert os.path.exists(kept) and open(kept, "rb").read() == b"raw-cut"
    assert monitor.clips_saved == []


def test_abort_keeps_raw_cuts_without_processing(tmp_path):
    out_dir = tmp_path / "clips"
    out_path = str(out_dir / "live-z.mp4")
    called = []
    monitor = LiveMonitor("u", str(out_dir),
                          process_fn=lambda *a, **k: called.append(1))
    monitor.stop(abort_processing=True)
    _run_workers_once(monitor, out_path)
    assert not called
    assert os.path.exists(str(out_dir / "live-z-raw.mp4"))
