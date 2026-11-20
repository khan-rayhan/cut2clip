# Phase 3 — Auto-framing and caption pipeline

## Goal
Turn a 40-second landscape clip into a finished 1080x1920 vertical
Short: the subject stays centred and tracked, captions pop up
word by word in the Hormozi style, and the output is H.264/AAC
MP4. No GUI yet. Command line only.

## Verified facts (research done 2026-11-18)
- The user PC has an NVIDIA GPU, so the YOLOv8 path and
  faster-whisper on CUDA are built. This VM is CPU-only, so tests
  run on CPU with the tiny whisper model and the MediaPipe path;
  the YOLOv8 path is built with a lazy import and tested on CPU
  with the nano model.
- MediaPipe Face Detection is the primary detector: CPU-friendly
  and good for talking heads. YOLOv8 person detection is the
  fallback when no face is found, and the GPU path on the user
  machine.
- YOLOv8 runs through ONNX Runtime (yolov8n.onnx, 12 MB), not
  ultralytics plus torch: the torch install is ~2 GB and took over
  18 minutes through this proxy before it was stopped. ONNX
  Runtime is already a faster-whisper dependency. On the user PC
  the CUDA execution provider can be used when a GPU is present.
- MediaPipe 1.x removed the legacy Solutions API, so face
  detection uses the Tasks API with the BlazeFace model
  (`models/blaze_face_short_range.tflite`). The Tasks native
  library needs libEGL.so.1 and libGLESv2.so.2, which this VM
  lacks; the .debs were extracted to `~/mediapipe-libs` and the
  test runs with that folder on LD_LIBRARY_PATH. The packaged
  app will need those libraries bundled or installed.
- faster-whisper 1.2.1 needs `av` below 14 (`metadata_errors`
  was removed in av 14); pinned `av>=11,<14`.
- faster-whisper gives word-level timestamps. The ASS file uses
  one event per word with karaoke timing so the current word is
  highlighted, in the big bold yellow-on-black Hormozi style.

## Tasks

### 3.1 Framing (`src/framing.py`)
- `detect_faces_mediapipe(frame)`: returns a list of boxes
  (x, y, w, h) in pixels, or an empty list.
- `detect_persons_yolo(frame)`: lazy ultralytics import, YOLOv8n
  person boxes, or an empty list when the model is unavailable.
- `Framer`: samples the video every 0.5 seconds, picks the
  subject box (largest face, else largest person, else centre),
  and smooths the crop centre with an exponential moving average
  (alpha 0.3) so the frame never jumps.
- Layout rule: one subject means a full 9:16 crop tracking that
  subject. Two or more subjects held for at least 3 seconds means
  split-screen: content on top, speaker on the bottom.
- `reframe_video(input, output)`: reads frames with OpenCV, crops
  per frame from the smoothed trajectory, writes 1080x1920 video,
  then muxes the original audio back with ffmpeg.
- Check: synthetic moving boxes produce a smooth crop that stays
  inside the frame; a real talking-head clip reframes to exactly
  1080x1920; no face in a clip falls back to a centre crop.

### 3.2 Captions (`src/captions.py`)
- `transcribe_words(path, model="tiny", device="auto")`: extracts
  audio with ffmpeg and runs faster-whisper with
  `word_timestamps=True`. Returns a list of (start, end, word).
  Device is CUDA when a GPU is present, otherwise CPU.
- `words_to_ass(words, ...)`: writes an ASS file, one event per
  word, grouped into lines of at most 3 words, karaoke highlight
  on the current word, 64pt bold, yellow current word, white rest,
  thick black outline, centred low on the frame.
- `burn_captions(video, ass, output)`: ffmpeg `ass` filter,
  re-encode H.264/AAC.
- Check: synthetic words produce an ASS file whose first and last
  events match the word times; a real 15-second audio clip
  transcribes to words covering the audio; burning captions into
  a 10-second video changes the pixels and keeps the duration.

### 3.3 Pipeline (`src/pipeline.py`)
- `process_clip(input, output, model="tiny")`: reframe, then
  transcribe, then burn captions. Each step logs its timing.
  Options skip reframing or captions for testing.
- Check: a synthetic 10-second clip with a moving subject and a
  word list becomes a 1080x1920 captioned MP4 of the right
  duration.

### 3.4 CLI and tests (`src/cli.py`, `tests/`)
- `process <input.mp4> [--out OUT] [--model tiny|base]
  [--no-captions] [--no-reframe]`.
- Tests cover 3.1 on synthetic boxes plus a real clip, 3.2 on
  synthetic words plus real audio, and 3.3 end to end on a
  synthetic clip.
- Check: `python -m pytest tests/` passes and the `process`
  command produces a 1080x1920 MP4 from a real clip.

## Waves
- Wave 1: 3.1 (framing, no network model downloads beyond
  MediaPipe/YOLO weights).
- Wave 2: 3.2 (captions, whisper model download).
- Wave 3: 3.3, 3.4 (pipeline plus CLI, depend on 3.1 and 3.2).

## Verification criteria
- Every check above passes.
- Output is always 1080x1920, H.264/AAC, MP4.
- The crop never jumps more than 15 percent of the frame width
  between sampled points.
- Captions cover the spoken words; no word starts before the
  audio does.

## Out of scope for this phase
- Any GUI (Phase 4).
- Uploading or posting (after v1).
- Speaker diarisation and multi-speaker caption colours (v2).
