"""Тесты обёрток ffmpeg. ffmpeg обязателен в PATH (см. conftest)."""
from pathlib import Path

import pytest

from factory.ffmpeg_tools import PNG_MAGIC, FfmpegError, ensure_png


def test_ensure_png_converts_jpeg_saved_under_png_name(tmp_path, make_jpeg):
    """WaveSpeed отдаёт JPEG, а конвейер хранит кадр как NNN.png — чиним содержимое."""
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    assert dest.read_bytes()[:2] == b"\xff\xd8"

    assert ensure_png(dest) == dest
    assert dest.read_bytes()[:8] == PNG_MAGIC


def test_ensure_png_leaves_real_png_byte_identical(tmp_path):
    """Настоящий PNG не трогаем — лишняя перекодировка запрещена."""
    dest = tmp_path / "001.png"
    original = PNG_MAGIC + b"payload-not-a-valid-png-body"
    dest.write_bytes(original)

    ensure_png(dest)
    assert dest.read_bytes() == original


def test_ensure_png_leaves_no_temp_files(tmp_path, make_jpeg):
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    ensure_png(dest)
    assert [p.name for p in tmp_path.iterdir()] == ["001.png"]


def test_ensure_png_restores_original_when_ffmpeg_fails(tmp_path):
    """Мусорные байты ffmpeg не декодирует (ненулевой код возврата) — оригинал
    должен вернуться на path нетронутым, FfmpegError пробросится, посторонних
    файлов в каталоге остаться не должно (скачанный кадр не теряется)."""
    dest = tmp_path / "001.png"
    original = b"this is not an image and ffmpeg cannot decode it" * 5
    dest.write_bytes(original)

    with pytest.raises(FfmpegError):
        ensure_png(dest)

    assert dest.read_bytes() == original
    assert [p.name for p in tmp_path.iterdir()] == ["001.png"]


# --- мастеринг громкости (дизайн 2026-09-04 §6.1) ---

def test_measure_loudness_parses_loudnorm_json(monkeypatch):
    from factory import ffmpeg_tools as ft
    stderr = (
        "some ffmpeg noise\n"
        "[Parsed_loudnorm_0 @ 000] \n"
        "{\n"
        '\t"input_i" : "-23.5",\n'
        '\t"input_tp" : "-2.1",\n'
        '\t"input_lra" : "7.2",\n'
        '\t"input_thresh" : "-34.0",\n'
        '\t"output_i" : "-14.0",\n'
        '\t"normalization_type" : "dynamic",\n'
        "}\n")
    monkeypatch.setattr(ft, "_run", lambda args, timeout=600: stderr)
    assert ft.measure_loudness(Path("x.mp4")) == pytest.approx(-23.5)


def test_measure_loudness_without_json_raises(monkeypatch):
    from factory import ffmpeg_tools as ft
    monkeypatch.setattr(ft, "_run", lambda args, timeout=600: "no json here")
    with pytest.raises(FfmpegError, match="loudnorm"):
        ft.measure_loudness(Path("x.mp4"))


def test_apply_gain_copies_video_stream(monkeypatch):
    # Мастеринг НЕ перекодирует картинку: это правило «монтаж только в Remotion».
    from factory import ffmpeg_tools as ft
    captured = {}
    monkeypatch.setattr(ft, "run_ffmpeg", lambda args: captured.setdefault("args", args))
    ft.apply_gain(Path("in.mp4"), Path("out.mp4"), 3.5)
    args = captured["args"]
    assert "-c:v" in args and args[args.index("-c:v") + 1] == "copy"
    assert any("volume=3.50dB" in a for a in args)


# --- обработка голоса (карточка Гвоздя: голос Устиньи с жестяным призвуком) ---

def test_voice_process_names_are_known():
    from factory.ffmpeg_tools import VOICE_PROCESSES
    assert "tin" in VOICE_PROCESSES


def test_apply_voice_process_builds_filter(monkeypatch, tmp_path):
    from factory import ffmpeg_tools as ft
    captured = {}
    monkeypatch.setattr(ft, "run_ffmpeg", lambda args: captured.setdefault("args", args))
    ft.apply_voice_process(tmp_path / "in.mp3", tmp_path / "out.mp3", "tin")
    args = captured["args"]
    assert "-af" in args
    chain = args[args.index("-af") + 1]
    # жестяной призвук — полоса плюс короткое эхо, как описано в карточке
    assert "highpass" in chain and "lowpass" in chain and "aecho" in chain


def test_apply_voice_process_unknown_name_raises(tmp_path):
    from factory.ffmpeg_tools import FfmpegError, apply_voice_process
    with pytest.raises(FfmpegError, match="tinn"):
        apply_voice_process(tmp_path / "in.mp3", tmp_path / "out.mp3", "tinn")


def test_measure_loudness_reads_real_ffmpeg_output(tmp_path):
    """Настоящий вызов ffmpeg, без подмены _run.

    Ревью 2026-09-05: loudnorm печатает JSON в stderr, а `_run` возвращал только
    stdout — с `-f null -` он всегда пуст. Функция падала на КАЖДОМ реальном
    вызове, `render._master` глотал это предупреждением, и мастеринг был тихой
    заглушкой. Тест с подменённым `_run` этого не видел: он проверял разбор
    строки, а не то, откуда строка берётся.
    """
    import subprocess

    from factory.ffmpeg_tools import measure_loudness
    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(src)],
        check=True, capture_output=True)
    lufs = measure_loudness(src)
    # Синус на полной шкале заведомо громче -40 LUFS и не тише 0
    assert -40.0 < lufs < 0.0
