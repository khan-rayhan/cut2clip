# Changelog

## v1.0.3 — 2026-11-24

### Added
- Per-clip processing progress in percent: the Pre-Recorded tab
  now shows the current clip's real progress (transcription 0–30%,
  subject tracking and the single encode 30–100%, reported
  frame-by-frame from the encoder), with the stage name and the
  clip number ("Clip 1 of 3 — 47% Reframing & encoding…") in the
  status bar. The Live monitor tab shows the same percent bar
  while a live clip is being processed.
- Aesthetic layout pass: a calm classic look — white theme:
  white background, black text, solid colors only (no
  gradients); every button now has one of four looks (black
  primary, muted-green accent, muted-red danger, quiet outline
  secondary for Browse); the progress bar got its own
  full-width row with a solid steel-blue chunk; the settings
  moved into two tidy rows (output folder on its own row,
  model/performance/captions/device on the second).
- Input boxes (URL, output folder, model/performance/captions/
  device pickers, spike threshold) are white with black text;
  the clip lists and the live log are white too. The spinbox
  up/down buttons and the combo drop-down arrow areas are
  white as well, so no part of an option box shows the default
  grey.
- The Live tab's spike threshold now shows its level next to
  the number (Low below 2.0, Medium 2.0–3.0, High above 3.0),
  updating as the number changes.
- Every dropdown (Whisper model, performance, captions, device)
  now shows a visible down chevron on its right side, so it is
  clear it opens a list (new `src/gui/down-arrow.png` asset,
  shipped in the installer via the spec's datas). The chevron
  sits inside its own light-grey arrow zone with a divider
  line, like a native dropdown.
- Background artwork: the main window now paints the space
  artwork (`src/gui/background.jpg`, shipped in the installer
  via the spec's datas) as its background, cover-scaled, with
  a slight darkening; every panel is frosted white glass over
  it so all text stays black-on-white and readable. The
  settings rows live in one frosted panel, the "Finished
  Clips" label is a frosted chip, and the checkboxes are black
  boxes with a white check (new `src/gui/check.png` asset).
- Liquid Glass panels (Apple-style): each big panel now shows
  the artwork genuinely blurred behind it (Gaussian-blurred
  copy painted in the main window, plus a light white tint),
  a bright rim around the edge, a specular highlight along
  the top edge, and a soft shadow underneath. The clip lists
  float directly on the tab pane's glass. True refraction
  (bending the artwork at the panel edges) is not possible
  in Qt, so the edges bend nothing — the blur, rim and
  shadow carry the look.
- The Spike threshold number now has a visible up/down arrow
  box next to it (new `src/gui/up-arrow.png` asset; the down
  arrow reuses the combo chevron), in its own light box with
  a divider, like the dropdown chevrons.
- The top "Cut2Clip" title lost its glass box: it is now
  plain text on the artwork, bigger (36px) and pastel green
  (#b5e7a0), with a bold dark edge around the letters (new
  `src/gui/outlined_label.py`: the glyph path is stroked,
  then filled) and a translucent blended fill so the artwork
  shows through the letters.
- Standard-library-only `src.doctor` diagnostics for Python
  modules, FFmpeg/ffprobe, NVIDIA driver visibility, RAM-based
  performance recommendation, and cached Whisper models.
  Supports readable and JSON reports (`python -m src.doctor`,
  `--json`).
- One-click Windows setup script (`scripts/setup_windows.bat`)
  for Python 3.12 virtual environment creation, dependency
  installation, and system diagnostics.
- Windows build script (`scripts/build_windows.bat`) that runs
  diagnostics and tests, creates the portable EXE, smoke-tests
  the packaged GUI, and optionally builds the Inno Setup
  installer.
- Expanded documentation for the YouTube pre-recorded workflow:
  heatmap/comment ranking, audio/transcript fallback, per-section
  download, Whisper transcription, vertical reframing, and MP4
  export.
- The GitHub Actions Windows workflow now runs the offline test
  suite and the doctor before packaging, and the packaged-GUI
  smoke test waits for the windowed exe and checks its exit
  code; before, it could not fail.
- Regression tests for each fix below
  (`tests/test_regressions_v105.py`).

### Changed
- The Pre-Recorded progress bar used to count finished clips
  (0 of 3, 1 of 3…); it now shows the current clip's percent,
  and the clip count moved to the status bar text.
- The Live tab's "Z threshold" setting is now called
  "Spike threshold" (same numbers, same behavior, plus a tooltip
  explaining it); the internal setting name is unchanged, so
  saved values carry over.
- The header bar now shows only "Cut2Clip" on the left.
- Capitalization is now consistent: buttons, tabs, section
  headers and dialog titles use Title Case ("Process
  Selected", "Auto-Clip Top 3", "Start Monitoring",
  "Pre-Recorded Clips", "Live Monitor", "Finished Clips",
  "Nothing Selected", "No Windows", "Clip Failed"); form
  labels stay in sentence case ("Output folder:",
  "Spike threshold:"). The bottom option dropdowns show a
  capital first letter ("Tiny", "Auto", "Hormozi", "TikTok",
  "CPU", "CUDA") while the stored values stay lowercase, so
  the pipeline and saved settings are unchanged.
- The bottom option labels and values are bold (same font and
  size): "Output folder:", the folder path, "Whisper model:",
  "Performance:", "Captions:", "Device:" and their values.
- The white boxes are now 70% transparent (30% white), so the
  space artwork shows through them strongly; the muted text
  was darkened and the info line and status bar made bold so
  the text stays readable on the artwork.
- The GUI now reports how many queued clips were saved versus
  failed instead of implying every clip succeeded, and no
  longer displays a duplicate failure dialog for one failed
  clip.
- Pre-recorded clip exports no longer silently overwrite files
  from earlier runs; the next available filename is selected.
- Pass-through processing (reframing and captions both
  disabled) now copies the original video instead of moving
  it into the output folder; same-path no-op is safe and
  same-path processing is rejected to protect the original.
- YouTube-backed test helpers invoke `yt_dlp` through the
  active Python interpreter instead of assuming a Linux-only
  `.venv/bin` path.
- The Inno Setup script now has a UTF-8 BOM, so the Bengali
  installer text renders correctly.

### Fixed
- **Pre-recorded clips came out empty.** The GUI created an
  empty temp `.mp4` before downloading, and yt-dlp treats an
  existing file as "already downloaded", so no section was
  fetched and the pipeline got a 0-byte file. The worker now
  downloads into a fresh folder, `download_section` forces
  `overwrites`, and a 0-byte result is reported as an error.
- **Live recorder failures were silent.** If ffmpeg died
  (network drop, expired URL, stream ended) monitoring carried
  on with an empty buffer. The monitor now detects it,
  reconnects up to 3 times with growing delays, reports
  progress in the log, and stops with a clear message if the
  stream is gone.
- **One bad clip could end all later clips.** Only
  `RingBufferError` was caught in the clip worker; any other
  error killed the thread. All errors are now caught, reported,
  and monitoring continues.
- **Busy chats fell behind.** The spike test scanned the whole
  5-minute baseline for every chat message. It now runs twice
  per second; every message is still counted.
- **Live chat ending was invisible.** The GUI log now says when
  chat stops, since spikes can no longer be detected.
- **Muxed streamlink streams crashed URL resolution**
  (`AttributeError: ... has no attribute 'url'`) instead of
  falling back to yt-dlp. A `.m3u8` URL with a query string is
  also recognised.
- Ring-buffer clip cutting no longer breaks on folder names
  containing an apostrophe.
- **Captions:** a time such as 59.996 s was written as the
  invalid `0:00:60.00`; words overlapping the next word caused
  caption flicker; `{`, `}` and `\` in a transcript could be
  parsed as ASS override tags.
- **Framing:** the crop path drifted ahead of the subject when
  `fps / sample_fps` was not a whole number (e.g. 25 fps), by
  about a second over a 40 s clip. Sources narrower than 9:16
  (tall phone video) were stretched; they are now cropped
  vertically. MediaPipe's detector is closed at exit, which
  removes a shutdown traceback.
- **Highlights:** a peak dropped for overlapping its neighbour
  near the start or end of a video was not replaced, so fewer
  than N clips were offered. Invalid timestamps such as `3:75`
  in comments are ignored.
- The installer spec listed `down-arrow.png` twice.

### Verification
- Full suite: **99 passed, 0 failed** (7 deselected — tests
  needing live YouTube access, Whisper model downloads, or
  real-time playback). The 17 new regression tests fail 16 of
  17 against the previous code, confirming the fixes address
  real defects.
- Real 15s end-to-end render (Rick Astley 18–33s, tiny,
  Hormozi): 1080x1920 H.264 + AAC, exactly 15.000s, 25 words
  transcribed, subject reframed, Hormozi captions burned in —
  25.0s total.
- Still untested on a real PC: live-stream run, CUDA caption
  speed, Windows installer build, macOS build.

## v1.0.2 — 2026-11-20

### Performance
- Added Auto, Lite, Balanced and Fast profiles. Auto selects a profile using physical RAM and CPU core count; Lite reduces frame sampling and detector input resolution for low-end PCs.
- Reworked reframing to stream frames directly to FFmpeg instead of writing an intermediate MPEG-4 file and re-encoding it.
- When captions and reframing are both enabled, ASS subtitles are burned during the same final encode.
- Added one-time probes for NVIDIA NVENC, Intel Quick Sync and AMD AMF; falls back to tuned x264 when no hardware encoder passes the probe.
- Cached the active faster-whisper model between clips, enabled greedy decoding for faster short-clip transcription, and used CTranslate2 for CUDA availability detection without requiring PyTorch. (VAD was tried here and removed: it drops sung vocals on real song audio, returning zero words.)
- Scaled detector input frames and bounded ONNX Runtime CPU threads; prefer CUDAExecutionProvider when available.
- Put temporary processing files on the output volume to avoid cross-volume copies.
- Connected performance and device settings through the GUI, live processing and CLI.
- Updated package version metadata to 1.0.2.

### Fixed
- Certificate errors no longer silently disable TLS verification: yt-dlp now retries against the OS certificate store (`compat_opts={'no-certifi'}`), which holds a corporate/MITM proxy CA that certifi's bundled store lacks. Disabling verification now needs the explicit opt-in `CUT2CLIP_ALLOW_INSECURE_YTDLP=1`.
- Installer version was 1.0.1 while the code said 1.0.2; all version metadata (code, pyproject, installer, changelog) now says 1.0.2.

### Verification
- Full suite: 74 tests. First full run: 73 passed, 1 failed — the
  failure was a real regression: `vad_filter=True` dropped all words
  on real song audio (0 words on Rick Astley 30–45s, where the old
  settings return 42). VAD was removed (greedy decoding kept);
  the caption + pipeline tests (16) then re-ran green, so all 74
  tests pass. Two stale test fakes were also fixed (GUI worker now
  accepts `device`/`performance_mode`; live-monitor fake accepts
  `performance_mode`/`device`).
- Real 15s end-to-end render (Rick Astley 18–33s, tiny, Hormozi,
  performance auto → lite on this VM): 1080x1920 h264 + AAC,
  exactly 15.000s, 25 words transcribed, subject reframed,
  Hormozi captions burned in — 26.1s total (transcribe 5.3s +
  single-encode reframe 20.7s), about 10x faster than the old
  two-pass pipeline (~259s for the same 15s).
- TLS: real download retried against the OS certificate store
  after the certifi bundle failed (verification stays on).
- Still untested on a real PC: live-stream run, CUDA caption
  speed, macOS build.

## v1.0.1 — 2026-11-20

### Added
- Modern dark UI: gradient hero header, violet-to-pink gradient
  buttons, styled tabs, lists and log. The live Start button turns
  red while monitoring is running.
- GUI theme tests that build the main window offscreen and verify
  the theme and a realistic pre-recorded state render.
- C2C app icon: bold white C2C letters with a violet-to-pink-to-orange glow on a dark navy tile, matching the GUI theme. The Windows installer and the exe now carry it.
- Three new caption styles alongside Hormozi (still the default): **TikTok** — words cycle through bright pink, yellow, cyan and green, the current word pops bigger; **karaoke** — the current word is bright white and pops, un-sung words are dimmed grey; **neon** — bold white words with a thick cyan outline glow, the current word in magenta. Picked in the GUI settings (remembered between runs) or with the CLI `--caption-style` flag (`process` and `live`).
- **Auto-clip top 3**: after Detect on a pre-recorded video, one button processes the top 3 highlight windows automatically — no ticking needed.
- **Comment spikes** for pre-recorded ranking: comments that mention a timestamp ("1:23", "1:02:03") vote for that moment, so a scene viewers kept commenting on can outrank a slightly stronger replay peak nobody mentioned (60% heatmap + 40% comment density). Fetched with plain yt-dlp, no API key, capped at 100 comments; when comments are disabled or unavailable the heatmap alone is used.

### Changed
- Renamed the app from Shorts App to Cut2Clip: GitHub repo `khan-rayhan/shorts-app` → `khan-rayhan/cut2clip`, installer `Cut2Clip-Setup-*.exe`, exe `cut2clip.exe`, window title and hero text, CLI program name, and package name. Saved settings are kept (the settings location is unchanged).
- Pre-recorded section downloads now allow up to 1080p instead of 720p, preferring H.264 (`avc1`) with a fallback chain: `bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba[ext=m4a]/b[height<=1080][ext=mp4]`. A 40-second 1080p section is about 30–60 MB, so the download size is not a concern; the H.264 preference still avoids the VP9/webm downloads that stall on some proxies. Audio stays `m4a` on purpose — plain best-audio picks Opus/Vorbis, which cannot go into an MP4, so yt-dlp would switch the output to MKV instead.
- The mode formerly called "VOD" is now **Pre-Recorded** everywhere the user sees it: GUI tab and labels, CLI messages, README. Internal names (e.g. `VodClipWorker`) are unchanged.

### Fixed
- Windows: captions failed to burn because the `.ass` path (`C:\...`) was passed to the ffmpeg filter unquoted. The path is now quoted and escaped.
- Split-screen layout stretched the picture (a round object came out 1.74x too tall on top and 0.80x too squat below). Panels now keep the source aspect ratio; the top panel sits on a blurred copy instead of being stretched.
- Live mode saved raw 16:9 cuts. Every live clip now goes through reframe and captions. Cutting and processing run in separate workers so a slow render never lets the 80s buffer expire. A failed or interrupted clip keeps its raw cut as `<name>-raw.mp4`.
- The audio fallback downloaded the whole audio track to disk. It is now streamed through ffmpeg and scored in memory (`ingestion.download_audio` is replaced by `ingestion.audio_stream_source`; the CLI `--keep-audio` option is removed).
- `download_section` now checks the result with ffprobe and deletes it with an error if the file is far longer than requested.
- `process_clip` and `Framer.reframe_video` used fixed temp file names, so two clips processed at once overwrote each other.
- Closing the GUI or stopping the monitor no longer destroys a running worker thread, and the live buffer folder is deleted when monitoring stops.
- **Live monitor could not resolve any live stream** ("Could not resolve stream" with an empty cause) on the installed app. Root cause: streamlink 8.x loads its 138 built-in plugins lazily from `plugins/_plugins.json` and the `streamlink/plugins/*.py` modules, and the PyInstaller spec only listed `streamlink` as a hidden import — the bundle shipped streamlink with no plugins at all, so every URL failed with an empty `NoPluginError` (reproduced locally with the plugin files stripped). The spec now uses `collect_all("streamlink")` (it has no PyInstaller hook, so this is safe) plus the streamlink dist-info so the lazy-load checksum can run.
- Same class of bug, found by audit: `ctranslate2` has no hook either, and on Windows it glob-loads `*.dll` files out of its own package directory with `ctypes` — invisible to static analysis. The spec now uses `collect_all("ctranslate2")` too.
- As a backup for live resolving, `resolve_stream_url` now falls back to yt-dlp when streamlink fails or finds no stream, and the error names both causes instead of an empty message. The GUI live log now shows the full traceback for a monitor failure, so a future failure is diagnosable from the log alone.

## v1.0.0 — 2026-11-18

First release. A desktop app (Windows first, macOS second) that
turns video and live stream URLs into 40-second vertical
Shorts/Reels (9:16, 1080x1920, H.264/AAC, MP4).

### Added
- URL input with automatic VOD vs live detection (yt-dlp).
- Mode A (VOD): Most Replayed heatmap extraction, with an audio
  energy plus transcript hook-density fallback; non-overlapping
  40-second windows around the peaks.
- Mode B (live): chat velocity monitoring (Z-score > 2.5),
  80-second rolling ring buffer, 40-second clip per spike
  (t-20s to t+20s).
- Auto-framing: MediaPipe face detection with EMA smoothing,
  YOLOv8n (ONNX Runtime) fallback, split-screen for multiple
  speakers.
- Auto-captions: faster-whisper word timestamps, Hormozi-style
  pop-up subtitles burned in with FFmpeg.
- PySide6 GUI: detect, VOD clip list, live monitor, job queue,
  progress, finished-clip list, persistent settings.
- PyInstaller one-file build (Windows guide in
  `packaging/build-windows.md`).

### Fixed during final verification
- `download_section` downloaded the whole video instead of the
  40-second window: the Python API has no `download_sections`
  option — the CLI strings map to a `download_ranges` callback.
  Also capped formats to 720p MP4 (uncapped picked a 229 MB 4K
  AV1 file; generic `bv*+ba` picked webm that stalls on some
  proxies).
- `process` failed at the last step when the output folder was
  on a different filesystem from /tmp (`os.replace` cannot
  rename across filesystems). The final move now uses
  `shutil.move`.
- The bundle spec now also collects libEGL/libGLESv2 from the
  durable `~/mediapipe-libs` copies, so a VM replacement no
  longer produces a bundle that fails at startup with
  "ImportError: libEGL.so.1".

### Known issues
- The real live-stream run could not be completed on the build
  VM (streamlink cannot reach YouTube through the VM's proxy);
  monitor logic is proven by synthetic burst tests. First live
  run on a real PC is a manual check.
- The macOS build is untested (no Mac was available).
- First launch of the one-file bundle is slow (it unpacks
  itself); Whisper models download on first use (~75 MB for
  tiny).
- MediaPipe prints a harmless `TypeError: 'NoneType' object is
  not callable` warning from its FaceDetector teardown at
  shutdown. It does not affect the output.
- Facebook live chat is not supported in v1 (needs login/API
  approval). YouTube and Twitch first.
