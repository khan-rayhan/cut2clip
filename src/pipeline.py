"""Memory-conscious, single-encode clip processing pipeline."""

from __future__ import annotations

import os
import shutil
import tempfile
import time

from . import captions, framing
from .performance import get_profile


def process_clip(input_path: str, output_path: str,
                 model: str = "tiny",
                 do_reframe: bool = True,
                 do_captions: bool = True,
                 caption_style: str = "hormozi",
                 log=print,
                 device: str = "auto",
                 performance_mode: str = "auto",
                 progress_cb=None) -> str:
    """Process a clip with bounded-memory intermediates and one video encode.

    Transcription is performed on the source before re-framing. When both
    re-framing and captions are enabled, FFmpeg burns the ASS subtitles in the
    same encode that writes the vertical video, avoiding a second lossy pass.
    ``progress_cb`` (optional) is called as ``progress_cb(frac, label)``
    with ``frac`` 0..1 across the whole clip: transcription 0-0.30,
    subject tracking and the encode 0.30-1.0 (the encode reports real
    frame-by-frame progress; without captions the encode spans 0-1.0).
    """
    started = time.time()
    input_abs = os.path.normcase(os.path.realpath(os.path.abspath(input_path)))
    output_abs = os.path.normcase(os.path.realpath(os.path.abspath(output_path)))
    same_path = input_abs == output_abs
    if same_path and (do_reframe or do_captions):
        raise ValueError("Input and output paths must be different; the original video is protected.")
    if same_path:
        log("No processing requested; source file left unchanged.")
        if progress_cb is not None:
            progress_cb(1.0, "Done (no changes)")
        return input_path

    profile = get_profile(performance_mode)
    selected_model = model or profile.whisper_model
    log(f"Performance profile: {profile.name}")
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    # Keep temporary files on the destination volume so final promotion is
    # an atomic rename rather than a potentially expensive cross-drive copy.
    work = tempfile.mkdtemp(prefix="cut2clip-", dir=output_dir)
    # Transcription takes the first 30% of the bar when captions are on;
    # otherwise the encode spans the whole bar.
    base = 0.30 if do_captions else 0.0
    span = 1.0 - base

    def _emit(frac: float, label: str) -> None:
        if progress_cb is not None:
            progress_cb(max(0.0, min(1.0, frac)), label)

    try:
        ass_path = None
        if do_captions:
            step = time.time()
            _emit(0.02, "Transcribing…")
            # First run downloads the Whisper model (~75 MB) inside
            # transcribe_words with no progress of its own, so the bar
            # freezes at the transcribe step. Say so up front; when a
            # model is already cached this stays silent.
            from .doctor import _whisper_cache_status
            _cached, _ = _whisper_cache_status()
            if not _cached:
                log("First run: downloading the Whisper caption model "
                    "(about 75 MB) — the bar will pause here, then "
                    "transcription starts.")
            words = captions.transcribe_words(input_path, model=selected_model,
                                               device=device,
                                               cpu_threads=profile.ffmpeg_threads)
            log(f"Transcribed {len(words)} words with {selected_model} in {time.time() - step:.1f}s")
            _emit(base, f"Transcribed {len(words)} words")
            ass_path = os.path.join(work, "captions.ass")
            captions.words_to_ass(words, ass_path, style=caption_style)

        if do_reframe:
            step = time.time()
            _emit(base, "Finding subject…")
            framer = framing.Framer(input_path, performance_mode=performance_mode)
            layout = framer.compute_trajectory()
            staged_output = os.path.join(work, "final.mp4")
            framer.reframe_video(
                staged_output, ass_path=ass_path,
                progress_cb=lambda f: _emit(base + span * f,
                                            "Reframing & encoding…"))
            log(f"Reframed ({layout}) and encoded in {time.time() - step:.1f}s")
            current = staged_output
        elif ass_path:
            step = time.time()
            current = os.path.join(work, "captioned.mp4")
            captions.burn_captions(input_path, ass_path, current,
                                   performance_mode=performance_mode,
                                   progress_cb=lambda f: _emit(
                                       base + span * f, "Burning captions…"))
            log(f"Captions burned in {time.time() - step:.1f}s")
        else:
            current = input_path

        if os.path.abspath(current) != os.path.abspath(output_path):
            if os.path.abspath(current) == os.path.abspath(input_path):
                # Pass-through mode must never move the user's original file.
                # copy2 preserves metadata and leaves the source available.
                shutil.copy2(input_path, output_path)
            else:
                # The work folder is on the output volume, so promotion is atomic.
                os.replace(current, output_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    _emit(1.0, "Done")
    log(f"Done in {time.time() - started:.1f}s -> {output_path}")
    return output_path
