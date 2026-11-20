"""Tests for caption generation and burning."""

import subprocess

import cv2
import pytest

from src.captions import (burn_captions, transcribe_words, words_to_ass,
                          _ass_time)


def test_ass_time():
    assert _ass_time(65.5) == "0:01:05.50"
    assert _ass_time(0.0) == "0:00:00.00"
    assert _ass_time(3661.25) == "1:01:01.25"


def test_words_to_ass(tmp_path):
    words = [(0.0, 0.4, "Never"), (0.4, 0.8, "gonna"),
             (0.8, 1.2, "give"), (1.2, 1.6, "you"),
             (1.6, 2.0, "up")]
    ass = tmp_path / "caps.ass"
    words_to_ass(words, str(ass))
    text = ass.read_text()
    events = [line for line in text.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 5  # one event per word
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.40,")
    # The current word is yellow, the rest of its line is plain.
    assert "{\\c&H00FFFF&}Never{\\c&HFFFFFF&}" in events[0]
    assert "gonna" in events[0] and "give" in events[0]
    # Word 4 starts a new line of three, so it must not share a
    # line with words 1-3.
    assert "Never" not in events[3]
    assert "you" in events[3] and "up" in events[3]


def _make_video(path, duration=10):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i",
         f"color=c=black:size=1280x720:rate=30:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", path],
        check=True)


def _duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], text=True)
    return float(out.strip())


def _caption_region_mean(path, seconds=4.25):
    """Mean brightness of the bottom-centre band where captions land
    (Alignment 2, MarginV 260 on a 1080x1920 canvas)."""
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
    ok, frame = cap.read()
    cap.release()
    assert ok
    h, w = frame.shape[:2]
    band = frame[int(h * 0.75):h, int(w * 0.25):int(w * 0.75)]
    return band.mean()


def test_burn_captions_changes_pixels(tmp_path):
    src = tmp_path / "src.mp4"
    _make_video(str(src))
    words = [(4.0, 4.5, "HELLO"), (4.5, 5.0, "WORLD"), (5.0, 5.5, "TEST")]
    ass = tmp_path / "caps.ass"
    words_to_ass(words, str(ass))
    out = tmp_path / "captioned.mp4"
    burn_captions(str(src), str(ass), str(out))
    assert abs(_duration(str(out)) - 10.0) < 0.6
    # Bright caption text mid-word must change the caption band visibly.
    assert _caption_region_mean(str(out)) - _caption_region_mean(str(src)) > 1.0


def test_transcribe_real_audio(tmp_path):
    audio = tmp_path / "rick.m4a"
    yt_dlp = str(__import__("pathlib").Path(__file__).parent.parent
                 / ".venv" / "bin" / "yt-dlp")
    dl = subprocess.run(
        [yt_dlp, "-q", "--no-check-certificate",
         "-f", "ba",
         "--download-sections", "*00:00:30-00:00:45",
         "-o", str(audio),
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        capture_output=True, text=True)
    if dl.returncode != 0 or not audio.exists():
        pytest.skip("Could not download the test audio (network).")
    words = transcribe_words(str(audio), model="tiny", device="cpu")
    assert len(words) > 10
    assert words[-1][1] > 10.0  # words cover most of the 15s clip
    assert all(0 <= s < e for s, e, _ in words)


# ---------------------------------------------------------------- caption paths

def test_filter_path_quotes_and_escapes_windows_paths():
    from src.captions import filter_path
    assert (filter_path(r"C:\Users\me\AppData\Local\Temp\a.ass")
            == "'C\\:/Users/me/AppData/Local/Temp/a.ass'")
    assert filter_path("/tmp/a,b[1].ass") == "'/tmp/a,b[1].ass'"


def test_burn_captions_with_colon_in_path(tmp_path):
    """A ':' in the path (every Windows drive letter has one) used to make
    ffmpeg fail with "Unable to parse option value"."""
    import subprocess

    from src.captions import burn_captions, words_to_ass

    folder = tmp_path / "dir:with:colon"
    folder.mkdir()
    video = folder / "in.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "color=c=blue:size=1080x1920:rate=10:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
        check=True)
    ass = words_to_ass([(0.2, 0.8, "hello"), (0.9, 1.5, "world")],
                       str(folder / "c.ass"))
    out = burn_captions(str(video), ass, str(folder / "out.mp4"))
    assert (folder / "out.mp4").stat().st_size > 0 and out
