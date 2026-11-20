"""Auto-captioning for Phase 3: faster-whisper word timestamps
turned into Hormozi-style pop-up ASS subtitles, burned in with
FFmpeg.

Style: big bold words low on the frame, the current word in yellow,
the rest white, thick black outline. Words are grouped into lines
of at most three so the eye never has to scan far; each word gets
its own event, shown for exactly that word's timespan.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

WORDS_PER_LINE = 3


def _ass_time(seconds: float) -> str:
    """Seconds to ASS time H:MM:SS.cc."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _line_text(group: list[tuple[float, float, str]], current: int) -> str:
    """The line's words with the ``current`` one in yellow, the rest
    white. ASS colours are &HBBGGRR&: yellow is &H00FFFF&."""
    parts = []
    for j, (_s, _e, word) in enumerate(group):
        if j == current:
            parts.append("{\\c&H00FFFF&}%s{\\c&HFFFFFF&}" % word)
        else:
            parts.append(word)
    return " ".join(parts)


def words_to_ass(words: list[tuple[float, float, str]], out_path: str) -> str:
    """Write an ASS file from (start, end, word) tuples. Words are
    grouped into lines of at most three; each word gets its own
    event, shown for exactly that word's timespan, with the current
    word in yellow and the rest of its line in white."""
    lines = [ASS_HEADER]
    for i in range(0, len(words), WORDS_PER_LINE):
        group = words[i:i + WORDS_PER_LINE]
        for j, (start, end, _word) in enumerate(group):
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Default,,0,0,0,,{_line_text(group, j)}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return out_path


def transcribe_words(path: str, model: str = "tiny",
                     device: str = "auto") -> list[tuple[float, float, str]]:
    """Transcribe *path* (audio or video) with faster-whisper and
    return word-level (start, end, word) tuples. ``device`` is 'cuda'
    when a GPU is present, else 'cpu'."""
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    whisper = WhisperModel(model, device=device, compute_type=compute_type)
    segments, _info = whisper.transcribe(path, word_timestamps=True)
    words: list[tuple[float, float, str]] = []
    for segment in segments:
        for word in segment.words or []:
            text = word.word.strip()
            if text:
                words.append((word.start, word.end, text))
    return words


def extract_audio(video_path: str, out_path: str | None = None) -> str:
    """Extract the audio of *video_path* to a 16 kHz mono WAV."""
    out_path = out_path or os.path.join(tempfile.gettempdir(),
                                        "shorts-audio.wav")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", video_path,
           "-vn", "-ac", "1", "-ar", "16000", out_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {result.stderr[-300:]}")
    return out_path


def burn_captions(video_path: str, ass_path: str, output_path: str) -> str:
    """Burn the ASS subtitles into *video_path* with ffmpeg."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", video_path,
           "-vf", f"ass={ass_path}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "copy", "-movflags", "+faststart", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg caption burn failed: {result.stderr[-300:]}")
    return output_path
