"""Hardware-aware performance profiles for Cut2Clip.

The profiles favour predictable memory use on low-end machines. Optional
system-information packages are deliberately not required.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
import sys


@dataclass(frozen=True)
class PerformanceProfile:
    name: str
    sample_fps: float
    detection_width: int
    ffmpeg_preset: str
    crf: int
    ffmpeg_threads: int
    whisper_model: str


_HARDWARE_ENCODER_ARGS: list[str] | None = None


PROFILES = {
    "lite": PerformanceProfile("lite", 0.75, 480, "ultrafast", 25, 2, "tiny"),
    "balanced": PerformanceProfile("balanced", 1.5, 640, "veryfast", 23, 0, "tiny"),
    "fast": PerformanceProfile("fast", 2.0, 640, "superfast", 21, 0, "base"),
}


def total_memory_gb() -> float | None:
    """Return physical RAM in GiB without requiring psutil."""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) / 1024 / 1024
        if sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / (1024 ** 3)
        if sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2)
            return int(out.strip()) / (1024 ** 3)
    except Exception:
        return None
    return None


def recommended_mode() -> str:
    ram = total_memory_gb()
    cores = os.cpu_count() or 2
    if (ram is not None and ram <= 8) or cores <= 4:
        return "lite"
    if (ram is not None and ram >= 24) and cores >= 8:
        return "fast"
    return "balanced"


def get_profile(mode: str = "auto") -> PerformanceProfile:
    selected = recommended_mode() if mode == "auto" else mode
    try:
        return PROFILES[selected]
    except KeyError as exc:
        raise ValueError(f"Unknown performance mode {mode!r}; choose auto, lite, balanced or fast") from exc


def _working_hardware_encoder() -> list[str] | None:
    """Probe optional H.264 hardware encoders once, then cache the result."""
    global _HARDWARE_ENCODER_ARGS
    if _HARDWARE_ENCODER_ARGS is not None:
        return _HARDWARE_ENCODER_ARGS or None
    candidates = [
        ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-b:v", "0"],
        ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"],
        ["-c:v", "h264_amf", "-quality", "speed", "-qp_i", "23", "-qp_p", "23"],
    ]
    for args in candidates:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=64x64:r=1:d=0.2", "-frames:v", "1",
                 *args, "-pix_fmt", "yuv420p", "-f", "null", "-"],
                capture_output=True, text=True, timeout=8)
            if result.returncode == 0:
                _HARDWARE_ENCODER_ARGS = args
                return args
        except (OSError, subprocess.TimeoutExpired):
            continue
    _HARDWARE_ENCODER_ARGS = []
    return None


def ffmpeg_video_args(mode: str = "auto") -> list[str]:
    """Prefer a verified hardware H.264 encoder, otherwise use tuned x264."""
    p = get_profile(mode)
    hardware = _working_hardware_encoder()
    if hardware:
        return [*hardware, "-pix_fmt", "yuv420p"]
    args = ["-c:v", "libx264", "-preset", p.ffmpeg_preset, "-crf", str(p.crf),
            "-pix_fmt", "yuv420p"]
    if p.ffmpeg_threads > 0:
        args += ["-threads", str(p.ffmpeg_threads)]
    return args
