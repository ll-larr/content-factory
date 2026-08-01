"""Обёртка ffmpeg/ffprobe (спека фазы 2 §7–9).

Единственное место в кодовой базе, где запускаются бинари ffmpeg/ffprobe.
Ошибки — FfmpegError с полной командой для ручной диагностики.
"""
from __future__ import annotations

import os
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


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def ensure_png(path: Path) -> Path:
    """Гарантировать, что файл с именем *.png действительно PNG.

    WaveSpeed на image-моделях отдаёт JPEG, а конвейер хранит кадры под именем
    NNN.png — конвенция путей (factory.shots.frame_path), на неё ссылаются refs
    в shots.json. Имя менять нельзя, поэтому нормализуем содержимое.
    """
    path = Path(path)
    if path.read_bytes()[:8] == PNG_MAGIC:
        return path
    src = path.with_suffix(path.suffix + ".src")
    os.replace(path, src)
    try:
        run_ffmpeg(["-i", str(src), str(path)])
    finally:
        src.unlink(missing_ok=True)
    return path
