"""Phase 3 pipeline: reframe a clip to 1080x1920, transcribe it,
and burn Hormozi-style captions in. Each step logs its timing.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time

from . import captions, framing


def process_clip(input_path: str, output_path: str,
                 model: str = "tiny",
                 do_reframe: bool = True,
                 do_captions: bool = True,
                 caption_style: str = "hormozi",
                 log=print) -> str:
    """Full pipeline. Returns the output path. ``log`` receives the
    progress lines; the GUI passes a callback that forwards them to
    the log pane instead of stdout."""
    started = time.time()
    current = input_path
    # One private folder per call, so two clips processed at the same
    # time (live monitor plus a pre-recorded job) never overwrite each other.
    work = tempfile.mkdtemp(prefix="shorts-")
    try:
        if do_reframe:
            step = time.time()
            framer = framing.Framer(current)
            layout = framer.compute_trajectory()
            reframed = os.path.join(work, "reframed.mp4")
            framer.reframe_video(reframed)
            log(f"Reframed ({layout}) in {time.time() - step:.1f}s")
            current = reframed

        if do_captions:
            step = time.time()
            words = captions.transcribe_words(current, model=model)
            log(f"Transcribed {len(words)} words in {time.time() - step:.1f}s")
            ass_path = os.path.join(work, "captions.ass")
            captions.words_to_ass(words, ass_path, style=caption_style)
            captioned = os.path.join(work, "captioned.mp4")
            captions.burn_captions(current, ass_path, captioned)
            log(f"Captions burned in {time.time() - step:.1f}s")
            current = captioned

        if current != output_path:
            # shutil.move, not os.replace: the temp files live in /tmp
            # (tmpfs) while the output folder is usually on the main
            # disk, and a rename across filesystems fails with
            # "Invalid cross-device link". shutil.move copies instead.
            shutil.move(current, output_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    log(f"Done in {time.time() - started:.1f}s -> {output_path}")
    return output_path
