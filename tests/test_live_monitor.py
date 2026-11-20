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
    monitor = LiveMonitor("https://example.invalid/live", str(out_dir))
    # Short baseline so the test does not need 60s of history.
    monitor.velocity = ChatVelocity(min_baseline_s=10, baseline_s=60)
    saved = monitor.run(duration_s=60, chat_iter=_scripted_chat(),
                        stream_source=str(src))
    assert monitor.spikes_seen == 1
    assert len(saved) == 1
    assert abs(_duration(saved[0]) - 40.0) < 0.6
