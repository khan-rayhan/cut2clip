"""Auto-captioning for Phase 3: faster-whisper word timestamps
turned into pop-up ASS subtitles, burned in with FFmpeg.

Styles (``words_to_ass(..., style=...)``; Hormozi is the default):

- ``hormozi`` — big bold words low on the frame, the current word
  in yellow, the rest white, thick black outline.
- ``tiktok`` — each word cycles through bright pink / yellow /
  cyan / green, and the current word pops bigger.
- ``karaoke`` — the current word is bright white and pops bigger,
  the words not yet sung are dimmed grey.
- ``neon`` — bold white words with a thick cyan outline glow, the
  current word in magenta.

Words are grouped into lines of at most three so the eye never has
to scan far; each word gets its own event, shown for exactly that
word's timespan.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading

# ASS colours are &HBBGGRR&.
CAPTION_STYLES = ("hormozi", "tiktok", "karaoke", "neon")

# Reuse one Whisper model across sequential clips. Re-loading the model for
# every clip adds substantial startup latency and disk/RAM churn.
_WHISPER_CACHE_KEY = None
_WHISPER_CACHE_MODEL = None
_WHISPER_CACHE_LOCK = threading.Lock()

# TikTok palette: pink, yellow, cyan, green.
_TIKTOK_PALETTE = ("&H00A85CFF&", "&H000AD6FF&",
                   "&H00FFE500&", "&H006BFF7C&")
_KARAOKE_DIM = "&H00999999&"       # dim grey for words not yet sung
_NEON_CURRENT = "&H00FF00FF&"     # magenta current word
_NEON_OUTLINE = "&H00FFFF00&"     # cyan outline glow

# Per-style ASS Style line values: fontsize, primary, secondary,
# outline colour, outline width, shadow.
_STYLE_DEFS = {
    "hormozi": (64, "&H00FFFFFF&", "&H0000FFFF&", "&H00000000&", 4, 0),
    "tiktok": (68, "&H00FFFFFF&", "&H0000FFFF&", "&H00000000&", 5, 0),
    "karaoke": (64, "&H00999999&", "&H00FFFFFF&", "&H00000000&", 6, 2),
    "neon": (66, "&H00FFFFFF&", "&H00FF00FF&", "&H00FFFF00&", 8, 2),
}

_ASS_HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{fontsize},{primary},{secondary},{outline},&H00000000,-1,0,0,0,100,100,0,0,1,{border},{shadow},2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_header(style: str) -> str:
    """The ASS header for *style* (its Style line differs per style)."""
    fontsize, primary, secondary, outline, border, shadow = \
        _STYLE_DEFS[style]
    return _ASS_HEADER_TEMPLATE.format(
        fontsize=fontsize, primary=primary, secondary=secondary,
        outline=outline, border=border, shadow=shadow)


ASS_HEADER = _ass_header("hormozi")

WORDS_PER_LINE = 3


def _ass_time(seconds: float) -> str:
    """Seconds to ASS time H:MM:SS.cc."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _line_text(group: list[tuple[float, float, str]], current: int,
               style: str = "hormozi", start_index: int = 0) -> str:
    """The line's words with the ``current`` one highlighted, per
    style. ASS colours are &HBBGGRR&: yellow is &H00FFFF&.
    ``start_index`` is the group's first word in the whole caption,
    so the TikTok palette keeps cycling across line breaks instead
    of restarting on every line."""
    if style == "tiktok":
        # Every word wears a palette colour; the current word pops
        # bigger (\fs78 vs the style's 68) and resets afterwards.
        parts = []
        for j, (_s, _e, word) in enumerate(group):
            colour = _TIKTOK_PALETTE[
                (start_index + j) % len(_TIKTOK_PALETTE)]
            if j == current:
                parts.append("{\\fs78\\c%s}%s{\\c&HFFFFFF&\\fs68}"
                             % (colour, word))
            else:
                parts.append("{\\c%s}%s{\\c&HFFFFFF&}" % (colour, word))
        return " ".join(parts)
    if style == "karaoke":
        # Un-sung words stay the style's dim grey; the current word
        # is bright white and pops bigger, then resets to dim grey.
        parts = []
        for j, (_s, _e, word) in enumerate(group):
            if j == current:
                parts.append("{\\c&H00FFFFFF&\\fs76}%s{\\c%s\\fs64}"
                             % (word, _KARAOKE_DIM))
            else:
                parts.append(word)
        return " ".join(parts)
    if style == "neon":
        # White words with the cyan outline glow from the style;
        # the current word turns magenta.
        parts = []
        for j, (_s, _e, word) in enumerate(group):
            if j == current:
                parts.append("{\\c%s}%s{\\c&HFFFFFF&}"
                             % (_NEON_CURRENT, word))
            else:
                parts.append(word)
        return " ".join(parts)
    # hormozi: the current word is yellow, the rest of its line white.
    parts = []
    for j, (_s, _e, word) in enumerate(group):
        if j == current:
            parts.append("{\\c&H00FFFF&}%s{\\c&HFFFFFF&}" % word)
        else:
            parts.append(word)
    return " ".join(parts)


def words_to_ass(words: list[tuple[float, float, str]], out_path: str,
                 style: str = "hormozi") -> str:
    """Write an ASS file from (start, end, word) tuples. Words are
    grouped into lines of at most three; each word gets its own
    event, shown for exactly that word's timespan, highlighted
    according to ``style`` (one of CAPTION_STYLES)."""
    if style not in CAPTION_STYLES:
        raise ValueError(
            f"Unknown caption style {style!r}; "
            f"choose one of {', '.join(CAPTION_STYLES)}")
    lines = [_ass_header(style)]
    for i in range(0, len(words), WORDS_PER_LINE):
        group = words[i:i + WORDS_PER_LINE]
        for j, (start, end, _word) in enumerate(group):
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},"
                f"Default,,0,0,0,,{_line_text(group, j, style, start_index=i)}\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return out_path


def transcribe_words(path: str, model: str = "tiny",
                     device: str = "auto",
                     cpu_threads: int = 0) -> list[tuple[float, float, str]]:
    """Transcribe with a cached faster-whisper model and low-latency decoding.

    The model is loaded once and reused for subsequent clips. CPU inference
    uses int8; CUDA uses float16. Greedy decoding reduces work on short
    social clips while retaining word timestamps. (VAD was tried and
    removed: faster-whisper's VAD drops sung vocals on real song audio,
    returning zero words.)
    """
    global _WHISPER_CACHE_KEY, _WHISPER_CACHE_MODEL
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    cache_key = (model, device, compute_type, int(cpu_threads))
    with _WHISPER_CACHE_LOCK:
        if _WHISPER_CACHE_KEY != cache_key or _WHISPER_CACHE_MODEL is None:
            _WHISPER_CACHE_MODEL = WhisperModel(
                model, device=device, compute_type=compute_type,
                cpu_threads=max(0, int(cpu_threads)))
            _WHISPER_CACHE_KEY = cache_key
        whisper = _WHISPER_CACHE_MODEL

    segments, _info = whisper.transcribe(
        path, word_timestamps=True, beam_size=1)
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


def filter_path(path: str) -> str:
    """Quote and escape a file path for an ffmpeg filter argument.

    ffmpeg parses filter text twice, and ':' separates filter options,
    so an unquoted Windows path like C:\\Users\\me\\a.ass breaks the
    filter. Inside single quotes the path survives the first parse and
    only ':' needs a backslash for the second one: 'C\\:/Users/me/a.ass'.
    """
    s = str(path).replace("\\", "/").replace(":", "\\:")
    s = s.replace("'", "'\\''")
    return "'" + s + "'"


def burn_captions(video_path: str, ass_path: str, output_path: str,
                  performance_mode: str = "auto") -> str:
    """Burn ASS subtitles with the selected, hardware-aware encoder profile."""
    from .performance import ffmpeg_video_args
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", video_path,
           "-vf", f"ass={filter_path(ass_path)}",
           *ffmpeg_video_args(performance_mode),
           "-c:a", "copy", "-movflags", "+faststart", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg caption burn failed: {result.stderr[-300:]}")
    return output_path
