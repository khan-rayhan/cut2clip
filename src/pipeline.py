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
                 performance_mode: str = "auto") -> str:
    """Process a clip with bounded-memory intermediates and one video encode.

    Transcription is performed on the source before re-framing. When both
    re-framing and captions are enabled, FFmpeg burns the ASS subtitles in the
    same encode that writes the vertical video, avoiding a second lossy pass.
    """
    started = time.time()
    profile = get_profile(performance_mode)
    selected_model = model or profile.whisper_model
    log(f"Performance profile: {profile.name}")
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    # Keep temporary files on the destination volume so final promotion is
    # an atomic rename rather than a potentially expensive cross-drive copy.
    work = tempfile.mkdtemp(prefix="cut2clip-", dir=output_dir)
    try:
        ass_path = None
        if do_captions:
            step = time.time()
            words = captions.transcribe_words(input_path, model=selected_model,
                                               device=device,
                                               cpu_threads=profile.ffmpeg_threads)
            log(f"Transcribed {len(words)} words with {selected_model} in {time.time() - step:.1f}s")
            ass_path = os.path.join(work, "captions.ass")
            captions.words_to_ass(words, ass_path, style=caption_style)

        if do_reframe:
            step = time.time()
            framer = framing.Framer(input_path, performance_mode=performance_mode)
            layout = framer.compute_trajectory()
            staged_output = os.path.join(work, "final.mp4")
            framer.reframe_video(staged_output, ass_path=ass_path)
            log(f"Reframed ({layout}) and encoded in {time.time() - step:.1f}s")
            current = staged_output
        elif ass_path:
            step = time.time()
            current = os.path.join(work, "captioned.mp4")
            captions.burn_captions(input_path, ass_path, current,
                                  performance_mode=performance_mode)
            log(f"Captions burned in {time.time() - step:.1f}s")
        else:
            current = input_path

        if os.path.abspath(current) != os.path.abspath(output_path):
            # The work folder is on the output volume, so replace is atomic.
            os.replace(current, output_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    log(f"Done in {time.time() - started:.1f}s -> {output_path}")
    return output_path
