"""Обёртка ffmpeg (спека фазы 2 §7–9).

Единственное место в кодовой базе, где запускается бинарь ffmpeg.
Ошибки — FfmpegError с полной командой для ручной диагностики.

После переезда монтажа на Remotion (2026-09-02) здесь остался ровно один
потребитель — `ensure_png` из `generate_batch.py`. Чтение медиа (длительности,
fps, размеры) больше не делается на стороне Python вовсе: этим занимается
`parseMedia` внутри композиции, и `probe_duration`/`has_audio_stream` удалены
вместе с assemble.py и mix_audio.py. Заводить их заново — значит снова иметь
две стороны, читающие одни файлы разными способами.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


def _run(args: list[str], timeout: int = 600) -> str:
    """Выполнить команду и вернуть ОБА потока склеенными.

    Именно оба: ffmpeg пишет диагностику в stderr, и вывод фильтров тоже.
    Пока возвращался один stdout, `measure_loudness` не находил JSON вообще
    (с `-f null -` stdout всегда пуст) и падал на каждом реальном вызове —
    мастеринг громкости был тихой заглушкой (ревью 2026-09-05).
    """
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
    return result.stdout + result.stderr


def run_ffmpeg(args: list[str]) -> None:
    """Выполнить ffmpeg; args — всё после имени бинаря. Перезапись разрешена."""
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def ensure_png(path: Path) -> Path:
    """Гарантировать, что файл с именем *.png действительно PNG.

    Провайдер может отдать не-PNG (например JPEG) под именем NNN.png — конвенция
    путей (factory.shots.frame_path), на неё ссылаются refs в shots.json. Имя
    менять нельзя, поэтому нормализуем содержимое.

    Если конвертация не удалась, исходные байты возвращаются на path нетронутыми
    (скачанный, уже оплаченный кадр не должен теряться), а FfmpegError
    пробрасывается дальше вызывающему.
    """
    path = Path(path)
    if path.read_bytes()[:8] == PNG_MAGIC:
        return path
    src = path.with_suffix(path.suffix + ".src")
    os.replace(path, src)
    try:
        run_ffmpeg(["-i", str(src), str(path)])
    except (FfmpegError, OSError):
        # Только то, чем конвертация может законно провалиться. Голый
        # `except Exception` вернул бы байты и на ошибке программиста, спрятав её.
        os.replace(src, path)
        raise
    src.unlink(missing_ok=True)
    return path


# --- мастеринг громкости (дизайн 2026-09-04 §6.1) ---

# Целевой уровень доставки. -14 LUFS — то, к чему приводит YouTube: серия, сведённая
# тише, будет им поднята, громче — прижата, и в обоих случаях не так, как мы хотели.
DEFAULT_TARGET_LUFS = -14.0

# Порог, ниже которого поправку не применяем. Перекодирование звука ради 0.2 dB
# стоит потери качества и времени, а на слух такая разница не существует.
GAIN_EPSILON_DB = 0.5


def measure_loudness(path: Path) -> float:
    """Интегральная громкость файла в LUFS (фильтр loudnorm, режим анализа).

    Один проход, ничего не пишет: `-f null`. Число берётся из JSON, который
    loudnorm печатает в stderr последним блоком.
    """
    out = _run([
        "ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
        "-af", "loudnorm=print_format=json", "-f", "null", "-",
    ])
    start = out.rfind("{")
    end = out.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise FfmpegError(
            f"loudnorm не вернул JSON для {path} — громкость не измерена")
    block = out[start:end + 1]
    # loudnorm печатает JSON с висящей запятой перед закрывающей скобкой,
    # поэтому json.loads на нём падает: берём нужное поле разбором строк.
    for line in block.splitlines():
        if '"input_i"' in line:
            try:
                return float(line.split(":")[1].strip().strip('", '))
            except (IndexError, ValueError):
                break
    raise FfmpegError(f"loudnorm не вернул input_i для {path}")


def apply_gain(src: Path, dest: Path, gain_db: float) -> Path:
    """Скопировать файл, изменив только громкость звука на gain_db.

    Видеодорожка копируется байт в байт (`-c:v copy`): это мастеринг, а не
    монтаж. Правило репозитория — склейка и сведение живут только в Remotion,
    и перекодирование картинки здесь означало бы второй монтажный путь.
    """
    run_ffmpeg([
        "-i", str(src),
        "-af", f"volume={gain_db:.2f}dB",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(dest),
    ])
    return dest


# --- обработка голоса (дизайн 2026-09-04) ---

# Именованные цепочки обработки. Нужны там, где голос персонажа ОПРЕДЕЛЁН через
# другой голос: по карточке Гвоздь говорит голосом Устиньи с жестяным призвуком
# и лёгкой задержкой, «будто из ведра». Второй голос тут не нужен — нужен тот же,
# обработанный, и обработка обязана быть одинаковой во всех сериях.
#
# Почему не моделью: `voice-clone` дал плохой результат (живая проба 2026-09-04),
# а описать «тот же голос, но из ведра» пресетной модели нечем — пресеты не
# смешиваются. Фильтр детерминирован и бесплатен.
VOICE_PROCESSES = {
    # Полоса телефонного диапазона + короткое эхо: жесть звучит как узкая полоса
    # с металлическим отражением. Значения подобраны под описание карточки, но
    # НЕ проверены на слух — первую же реплику Гвоздя надо послушать.
    "tin": "highpass=f=700,lowpass=f=3600,aecho=0.8:0.5:45:0.35",
}


def apply_voice_process(src: Path, dest: Path, name: str) -> Path:
    """Применить именованную обработку голоса к файлу реплики."""
    chain = VOICE_PROCESSES.get(name)
    if chain is None:
        raise FfmpegError(
            f"неизвестная обработка голоса {name!r}; "
            f"известны {sorted(VOICE_PROCESSES)}")
    run_ffmpeg(["-i", str(src), "-af", chain, str(dest)])
    return dest

