"""Packaging tests: the PyInstaller spec must ship every runtime
data file the app opens by path, or the installed app fails where
the source tree works."""

import re
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parent.parent / "cut2clip.spec"


def test_spec_collects_chat_downloader():
    """Regression: live chat died in the installed v1.0.3 with
    "No such file or directory: .../chat_downloader/formatting/
    custom_formats.json" because the spec never collected it."""
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(r"for package in \(([^)]*)\)", text)
    assert match is not None
    assert "chat_downloader" in match.group(1)


def test_chat_downloader_data_file_is_collectable():
    """The JSON chat-downloader opens at runtime must be among the
    files PyInstaller would collect for the package."""
    pytest.importorskip("PyInstaller",
                        reason="PyInstaller is only needed to build")
    from PyInstaller.utils.hooks import collect_data_files
    files = collect_data_files("chat_downloader")
    assert any(src.endswith("custom_formats.json") for src, _dest in files)
