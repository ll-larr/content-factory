"""Общие фикстуры фазы 2: крошечные медиафайлы через ffmpeg lavfi.

ffmpeg обязателен в окружении (спека фазы 2 §10) — отсутствие роняет тесты.
"""
import subprocess
from pathlib import Path

import pytest


def _ffmpeg(args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
        check=True)


@pytest.fixture
def make_clip():
    """Видеоклип-заглушка заданной длительности (lavfi color, 64x36, 8 fps)."""
    def _make(path, seconds):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=red:s=64x36:r=8:d={seconds}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
        return path
    return _make


@pytest.fixture
def make_tone():
    """Аудио-заглушка (lavfi sine 440 Гц, aac) заданной длительности."""
    def _make(path, seconds):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                 "-c:a", "aac", str(path)])
        return path
    return _make
