"""Command line for Phase 1: probe a URL and list highlight windows.

Usage:
    python -m src.cli probe <url>
    python -m src.cli clips <url> [-n N] [--keep-audio PATH]

``clips`` uses the Most Replayed heatmap when it exists. Otherwise it
downloads best audio to a temp file and falls back to audio energy
plus transcript hook density.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

from . import highlights, ingestion
from .live_monitor import LiveMonitor
from .pipeline import process_clip


def _fmt(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _print_windows(windows: list[highlights.ClipWindow]) -> None:
    if not windows:
        print("No highlight windows found.")
        return
    for i, w in enumerate(windows, 1):
        print(f"#{i}  {_fmt(w.start)} - {_fmt(w.end)}  "
              f"peak {_fmt(w.peak_time)}  score {w.score:.2f}  [{w.source}]")


def cmd_probe(args: argparse.Namespace) -> int:
    info = ingestion.probe(args.url)
    print(f"Title:    {info.title}")
    print(f"Duration: {_fmt(info.duration) if info.duration else 'live / unknown'}")
    print(f"Live:     {info.is_live}")
    print(f"Heatmap:  {len(info.heatmap)} points" if info.has_heatmap else "Heatmap:  none")
    print(f"Captions: {', '.join(info.auto_caption_urls) or 'none'}")
    return 0


def cmd_clips(args: argparse.Namespace) -> int:
    info = ingestion.probe(args.url)
    if info.duration is None:
        print("Live stream: use live mode (Phase 2), not clips.")
        return 1
    windows = highlights.heatmap_windows(info.heatmap, info.duration, top_n=args.n)
    if windows:
        print(f"Source: Most Replayed heatmap ({len(info.heatmap)} points)")
        _print_windows(windows)
        return 0
    print("No heatmap. Falling back to audio energy + transcript...")
    tmp = args.keep_audio
    own_tmp = tmp is None
    if own_tmp:
        fd, tmp = tempfile.mkstemp(suffix=".m4a")
        os.close(fd)
    try:
        ingestion.download_audio(args.url, tmp)
        caption_url = info.auto_caption_urls.get("en") or next(
            iter(info.auto_caption_urls.values()), None)
        windows = highlights.combined_windows(tmp, caption_url,
                                              info.duration, top_n=args.n)
        _print_windows(windows)
        return 0 if windows else 1
    finally:
        if own_tmp and os.path.exists(tmp):
            os.remove(tmp)


def cmd_live(args: argparse.Namespace) -> int:
    info = ingestion.probe(args.url)
    if not info.is_live:
        print("This URL is not a live stream. Use 'clips' for VODs.")
        return 1
    print(f"Monitoring live: {info.title}")
    print(f"Clips go to: {args.out}  (Ctrl+C to stop)")
    monitor = LiveMonitor(args.url, args.out, z_threshold=args.z)
    saved = monitor.run(duration_s=args.seconds, dry_run=args.dry_run)
    print(f"Done. Spikes: {monitor.spikes_seen}, clips saved: {len(saved)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shorts-app",
                                     description="40-second Shorts/Reels from URLs")
    sub = parser.add_subparsers(dest="command", required=True)
    p_probe = sub.add_parser("probe", help="Show metadata for a URL")
    p_probe.add_argument("url")
    p_probe.set_defaults(fn=cmd_probe)
    p_clips = sub.add_parser("clips", help="List ranked 40-second windows")
    p_clips.add_argument("url")
    p_clips.add_argument("-n", type=int, default=5, help="Max windows")
    p_clips.add_argument("--keep-audio", default=None,
                         help="Keep the downloaded audio at this path")
    p_clips.set_defaults(fn=cmd_clips)
    p_live = sub.add_parser("live", help="Monitor a live stream for chat spikes")
    p_live.add_argument("url")
    p_live.add_argument("--seconds", type=float, default=None,
                        help="Stop after N seconds (default: run until Ctrl+C)")
    p_live.add_argument("--out", default="live-clips",
                        help="Folder for saved clips")
    p_live.add_argument("--z", type=float, default=2.5,
                        help="Z-score trigger threshold")
    p_live.add_argument("--dry-run", action="store_true",
                        help="Log spikes without saving clips")
    p_live.set_defaults(fn=cmd_live)
    p_proc = sub.add_parser("process",
                            help="Reframe a clip to 1080x1920 and burn captions")
    p_proc.add_argument("input")
    p_proc.add_argument("--out", default="short-vertical.mp4",
                        help="Output MP4 path")
    p_proc.add_argument("--model", default="tiny",
                        help="Whisper model size (tiny, base, small, ...)")
    p_proc.add_argument("--no-captions", action="store_true",
                        help="Skip transcription and captions")
    p_proc.add_argument("--no-reframe", action="store_true",
                        help="Skip reframing, caption only")
    p_proc.set_defaults(fn=cmd_process)
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except ingestion.IngestionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def cmd_process(args: argparse.Namespace) -> int:
    process_clip(args.input, args.out, model=args.model,
                 do_reframe=not args.no_reframe,
                 do_captions=not args.no_captions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
