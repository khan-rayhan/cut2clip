from src import doctor


def test_diagnostics_report_has_core_sections(monkeypatch):
    monkeypatch.setattr(doctor, "_command_version", lambda command, args: (True, f"{command} test"))
    monkeypatch.setattr(doctor, "_whisper_cache_status", lambda: (False, "not cached"))
    report = doctor.collect_diagnostics()
    assert "python" in report
    assert "modules" in report and "yt-dlp" in report["modules"]
    assert report["ffmpeg"]["ok"] is True
    assert report["ffprobe"]["ok"] is True
    assert report["recommended_performance"] in {"lite", "balanced", "fast"}


def test_doctor_exit_code_requires_ffmpeg(monkeypatch):
    monkeypatch.setattr(doctor, "collect_diagnostics", lambda: {
        "python": "3.12", "platform": "test", "recommended_performance": "lite",
        "ram_gib": 8.0, "modules": {"PySide6 GUI": True},
        "ffmpeg": {"ok": False, "info": "missing"},
        "ffprobe": {"ok": True, "info": "ok"},
        "nvidia_gpu": {"ok": False, "info": "not found"},
        "whisper_model_cached": False, "whisper_model_info": "not cached",
    })
    assert doctor.print_report() == 1
