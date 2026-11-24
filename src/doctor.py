"""Dependency and runtime diagnostics for Cut2Clip.

This module intentionally uses only the Python standard library so it can
run before optional application dependencies have been installed.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_MODULES = {
    "yt-dlp": "yt_dlp",
    "NumPy": "numpy",
    "PySide6 GUI": "PySide6",
    "faster-whisper captions": "faster_whisper",
    "CTranslate2": "ctranslate2",
    "MediaPipe face detection": "mediapipe",
    "OpenCV": "cv2",
    "ONNX Runtime person detection": "onnxruntime",
    "Streamlink live streams": "streamlink",
    "Chat Downloader": "chat_downloader",
    "PyAV": "av",
}


def _command_version(command: str, args: list[str]) -> tuple[bool, str]:
    path = shutil.which(command)
    if not path:
        return False, "not found on PATH"
    try:
        result = subprocess.run([path, *args], capture_output=True, text=True,
                                timeout=8, check=False)
        line = (result.stdout or result.stderr).strip().splitlines()
        return result.returncode == 0, (line[0][:180] if line else path)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _whisper_cache_status() -> tuple[bool, str]:
    home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub = home / "hub"
    found = sorted(p.name for p in hub.glob("models--Systran--faster-whisper-*")) if hub.exists() else []
    if found:
        return True, ", ".join(found[:5])
    return False, "no Whisper model cached yet (downloads on first caption run)"


def collect_diagnostics() -> dict:
    modules = {}
    for label, module in REQUIRED_MODULES.items():
        try:
            present = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            present = False
        modules[label] = present

    ffmpeg_ok, ffmpeg_info = _command_version("ffmpeg", ["-version"])
    ffprobe_ok, ffprobe_info = _command_version("ffprobe", ["-version"])
    nvidia_ok, nvidia_info = _command_version("nvidia-smi", ["--query-gpu=name", "--format=csv,noheader"])
    if nvidia_ok:
        nvidia_info = nvidia_info.splitlines()[0][:180]

    try:
        from .performance import total_memory_gb, recommended_mode
        ram = total_memory_gb()
        recommended = recommended_mode()
    except Exception:
        ram, recommended = None, "lite"

    whisper_cached, whisper_info = _whisper_cache_status()
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "modules": modules,
        "ffmpeg": {"ok": ffmpeg_ok, "info": ffmpeg_info},
        "ffprobe": {"ok": ffprobe_ok, "info": ffprobe_info},
        "nvidia_gpu": {"ok": nvidia_ok, "info": nvidia_info},
        "ram_gib": round(ram, 1) if ram is not None else None,
        "recommended_performance": recommended,
        "whisper_model_cached": whisper_cached,
        "whisper_model_info": whisper_info,
    }


def print_report(as_json: bool = False) -> int:
    report = collect_diagnostics()
    if as_json:
        print(json.dumps(report, indent=2))
        return 0

    print("Cut2Clip system check")
    print(f"Python: {report['python']} ({report['platform']})")
    print(f"Recommended performance: {report['recommended_performance'].upper()}")
    if report["ram_gib"] is not None:
        print(f"RAM: {report['ram_gib']} GiB")
    print("\nDependencies:")
    missing = []
    for name, present in report["modules"].items():
        print(f"  [{'OK' if present else 'MISSING'}] {name}")
        if not present:
            missing.append(name)
    for tool in ("ffmpeg", "ffprobe", "nvidia_gpu"):
        item = report[tool]
        print(f"  [{'OK' if item['ok'] else 'OPTIONAL/MISSING'}] {tool}: {item['info']}")
    print(f"  [{'OK' if report['whisper_model_cached'] else 'FIRST-RUN DOWNLOAD'}] Whisper model: {report['whisper_model_info']}")
    if missing:
        print("\nInstall missing Python dependencies with: python -m pip install -r requirements.txt")
    if not report["ffmpeg"]["ok"] or not report["ffprobe"]["ok"]:
        print("Install FFmpeg and add its bin folder to PATH. Both ffmpeg and ffprobe are required.")
    return 1 if missing or not report["ffmpeg"]["ok"] or not report["ffprobe"]["ok"] else 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check Cut2Clip dependencies and runtime")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)
    return print_report(as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
