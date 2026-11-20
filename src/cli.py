"""Command line for Phase 1: probe a URL and list highlight windows.

Usage:
    python -m src.cli probe <url>
    python -m src.cli clips <url> [-n N]

``clips`` uses the Most Replayed heatmap when it exists. Otherwise it
streams the audio through ffmpeg (nothing is saved to disk) and falls
back to audio energy plus transcript hook density.
"""

from __future__ import annotations

import argparse
import sys

from . import highlights, ingestion
from .captions import CAPTION_STYLES
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
    comment_points, n_comments = ingestion.fetch_comment_points(
        args.url, info.duration)
    windows = highlights.heatmap_windows(
        info.heatmap, info.duration, top_n=args.n,
        comment_points=comment_points)
    if windows:
        source = f"Most Replayed heatmap ({len(info.heatmap)} points)"
        if comment_points and n_comments:
            source += f" + comment spikes ({n_comments} comments)"
        print(f"Source: {source}")
        _print_windows(windows)
        return 0
    print("No heatmap. Falling back to audio energy + transcript...")
    audio_url, headers = ingestion.audio_stream_source(args.url)
    caption_url = info.auto_caption_urls.get("en") or next(
        iter(info.auto_caption_urls.values()), None)
    windows = highlights.combined_windows(audio_url, caption_url,
                                          info.duration, top_n=args.n,
                                          audio_headers=headers)
    _print_windows(windows)
    return 0 if windows else 1


def cmd_live(args: argparse.Namespace) -> int:
    info = ingestion.probe(args.url)
    if not info.is_live:
        print("This URL is not a live stream. Use 'clips' for pre-recorded videos.")
        return 1
    print(f"Monitoring live: {info.title}")
    print(f"Clips go to: {args.out}  (Ctrl+C to stop)")
    monitor = LiveMonitor(args.url, args.out, z_threshold=args.z,
                          process=not args.no_process, model=args.model,
                          caption_style=args.caption_style)
    saved = monitor.run(duration_s=args.seconds, dry_run=args.dry_run)
    print(f"Done. Spikes: {monitor.spikes_seen}, clips saved: {len(saved)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cut2clip",
                                     description="40-second Shorts/Reels from URLs")
    sub = parser.add_subparsers(dest="command", required=True)
    p_probe = sub.add_parser("probe", help="Show metadata for a URL")
    p_probe.add_argument("url")
    p_probe.set_defaults(fn=cmd_probe)
    p_clips = sub.add_parser("clips", help="List ranked 40-second windows")
    p_clips.add_argument("url")
    p_clips.add_argument("-n", type=int, default=5, help="Max windows")
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
    p_live.add_argument("--model", default="tiny",
                        help="Whisper model size for captions")
    p_live.add_argument("--caption-style", default="hormozi",
                        choices=CAPTION_STYLES,
                        help="Caption style for live clips")
    p_live.add_argument("--no-process", action="store_true",
                        help="Save raw 16:9 cuts only (no reframe, no captions)")
    p_live.set_defaults(fn=cmd_live)
    p_proc = sub.add_parser("process",
                            help="Reframe a clip to 1080x1920 and burn captions")
    p_proc.add_argument("input")
    p_proc.add_argument("--out", default="short-vertical.mp4",
                        help="Output MP4 path")
    p_proc.add_argument("--model", default="tiny",
                        help="Whisper model size (tiny, base, small, ...)")
    p_proc.add_argument("--caption-style", default="hormozi",
                        choices=CAPTION_STYLES,
                        help="Caption style (hormozi, tiktok, karaoke, neon)")
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
                 do_captions=not args.no_captions,
                 caption_style=args.caption_style)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
