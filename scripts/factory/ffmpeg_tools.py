"""Обёртка ffmpeg/ffprobe (спека фазы 2 §7–9).

Единственное место в кодовой базе, где запускаются бинари ffmpeg/ffprobe.
Ошибки — FfmpegError с полной командой для ручной диагностики.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


def _run(args: list[str], timeout: int = 600) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, encoding="utf-8", errors="replace",
            timeout=timeout)
    except FileNotFoundError:
        raise FfmpegError(
            f"{args[0]} не найден в PATH — установите ffmpeg (winget)") from None
    except subprocess.TimeoutExpired:
        raise FfmpegError(
            f"Команда не завершилась за {timeout}с: {args!r}") from None
    if result.returncode != 0:
        raise FfmpegError(
            f"Команда завершилась с кодом {result.returncode}: {args!r}\n"
            f"stderr: {result.stderr[-2000:]}")
    return result.stdout


def run_ffmpeg(args: list[str]) -> None:
    """Выполнить ffmpeg; args — всё после имени бинаря. Перезапись разрешена."""
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args)


def probe_duration(path: Path) -> float:
    """Длительность медиафайла в секундах (ffprobe)."""
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return float(out.strip())
    except ValueError:
        raise FfmpegError(
            f"ffprobe не вернул длительность для {path}: {out!r}") from None


def has_audio_stream(path: Path) -> bool:
    """Есть ли в файле аудиопоток."""
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=codec_type", "-of",
                "default=noprint_wrappers=1:nokey=1", str(path)])
    return "audio" in out
