"""Сборка финального видео серии из отрезков (спека фазы 2 §8, основная §12).

Запускать из корня репозитория:
  python scripts/assemble.py --project projects/pilot --episode ep01

Гейт: все отрезки эпизода приняты ревью (done/accepted_with_notes), иначе
список + exit 3. Если существует audio/mix.m4a (scripts/mix_audio.py) —
дорожка накладывается; иначе сборка идёт без звука (позволяет собрать
видео до готовности звука). Склейка — единая перекодировка libx264 (при разных
разрешениях отрезков ffmpeg упадёт с понятной ошибкой — допустимо для v1).
Контроль длительности: факт против len(segments)*segment_seconds, допуск ±5%
(спека §12) — при выходе предупреждение, файл сохраняется, exit 0.

Коды выхода: 0 успех; 1 ошибка данных/ffmpeg; 3 отрезки не приняты ревью.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.ffmpeg_tools import FfmpegError, probe_duration, run_ffmpeg
from factory.manifest import Manifest, ManifestError
from factory.project import load_project
from factory.shots import load_shots

ACCEPTED = {"done", "accepted_with_notes"}
DURATION_TOLERANCE = 0.05  # ±5% (спека §12)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    project = load_project(project_dir / "project.json")
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")
    ep = shots["episode"]

    segments = shots["segments"]
    if not segments:
        print("В shots.json нет отрезков — собирать нечего.")
        return 1

    # Гейт: все отрезки приняты ревью (расширение гейта фазы 1 на отрезки)
    problems = {}
    for s in segments:
        item_id = f"{ep}/segments/{s['n']:03d}"
        try:
            status = manifest.get(item_id)["status"]
        except ManifestError:
            problems[item_id] = "не генерировался"
            continue
        if status not in ACCEPTED:
            problems[item_id] = f"статус {status}"
    if problems:
        print("ОТРЕЗКИ НЕ ПРИНЯТЫ РЕВЬЮ — сборка заблокирована:")
        for item_id in sorted(problems):
            print(f"  - {item_id}: {problems[item_id]}")
        return 3

    files = []
    for seg in sorted(segments, key=lambda item: item["n"]):
        f = episode_dir / "segments" / f"{seg['n']:03d}.mp4"
        if not f.exists():
            print(f"Файл отрезка не найден: {f}")
            return 1
        files.append(f)

    dest = episode_dir / "final" / f"{args.episode}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Не <имя>.mp4.tmp (конвенция репо): ffmpeg выбирает муксер по расширению,
    # поэтому .mp4 должен остаться последним суффиксом.
    tmp = dest.with_name(dest.stem + ".tmp.mp4")

    inputs: list[str] = []
    for f in files:
        inputs.extend(["-i", str(f)])
    n = len(files)
    filt = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    maps = ["-map", "[v]"]
    extra: list[str] = []
    mix = episode_dir / "audio" / "mix.m4a"
    audio_note = "без звука (audio/mix.m4a не найден)"
    if mix.exists():
        inputs.extend(["-i", str(mix)])
        maps.extend(["-map", f"{n}:a", "-c:a", "aac"])
        # -shortest — подстраховка: длительность mix == видео по построению (mix_audio.py)
        extra = ["-shortest"]
        audio_note = "со звуком"
    try:
        run_ffmpeg(inputs + ["-filter_complex", filt] + maps +
                   ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + extra
                   + [str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1

    try:
        fact = probe_duration(dest)
    except FfmpegError as e:
        print(f"ПРЕДУПРЕЖДЕНИЕ: не удалось проверить длительность: {e}")
        print(f"Собрано: {dest} ({n} отрезков, {audio_note}).")
        return 0
    plan = len(segments) * project.segment_seconds
    if abs(fact - plan) > plan * DURATION_TOLERANCE:
        print(f"ВНИМАНИЕ: длительность {fact:.2f}с вне допуска ±5% "
              f"от плановой {plan}с — проверьте отрезки.")
    print(f"Собрано: {dest} ({fact:.2f}с, {n} отрезков, {audio_note}).")
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
