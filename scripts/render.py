"""Монтаж эпизода: склейка, звук и оформление одной командой (спека 2026-08-31 §8).

Запускать из корня репозитория:
  python scripts/render.py --project projects/<проект> --episode ep01
  python scripts/render.py --project projects/<проект> --episode ep01 --format 9x16
  python scripts/render.py --project projects/<проект> --episode ep01 --audio-only
  python scripts/render.py --project projects/<проект> --episode ep01 --studio

Заменяет прежнюю пару mix_audio.py + assemble.py: склейка и сведение больше не
два процесса, Remotion делает их за один проход, поэтому промежуточного mix.m4a
в обычном пути нет — он остаётся только как предпрослушка (--audio-only).

Гейт: все отрезки И все аудио-единицы эпизода приняты ревью, иначе общий список
и exit 3. Раньше это были два разных скрипта, и человек узнавал о второй проблеме,
только починив первую.

Коды выхода: 0 успех; 1 ошибка данных или рендера; 3 не принято ревью.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory import environment, montage
from factory.audio_plan import AudioPlanError
from factory.ffmpeg_tools import (FfmpegError,
                                  GAIN_EPSILON_DB, apply_gain, measure_loudness)
from factory.manifest import Manifest
from factory.project import ProjectError, load_project
from factory.shots import ShotsError, load_shots

MONTAGE_DIR = Path("montage")
# Корень репозитория от файла, а не от текущего каталога: `montage/node_modules`
# принадлежит РЕПОЗИТОРИЮ, и спрашивать про них у случайного cwd бессмысленно.
ROOT = Path(__file__).resolve().parent.parent
COMPOSITIONS = {"16x9": "Episode16x9", "9x16": "Episode9x16"}


def run_node(cmd: list[str], cwd: Path = MONTAGE_DIR) -> int:
    """Выполнить команду Remotion. Вывод идёт напрямую в консоль пользователя:
    рендер длинный, прогресс важнее аккуратного захвата."""
    npx = shutil.which("npx") or "npx"
    return subprocess.run([npx] + cmd, cwd=str(cwd)).returncode


def _fail(header: str, lines) -> int:
    print(header)
    for line in lines:
        print(f"  - {line}")
    return 1


def _master(dest: Path, target_lufs: float) -> int:
    """Привести громкость готового файла к целевому уровню.

    Измеряем — считаем поправку — применяем. Ошибка мастеринга НЕ отменяет уже
    отрендеренный эпизод: файл на месте, ему просто не поправили уровень, и
    сказать об этом честнее, чем вернуть провал всего рендера.
    """
    try:
        measured = measure_loudness(dest)
    except FfmpegError as e:
        print(f"ВНИМАНИЕ: громкость не измерена ({e}); файл оставлен как есть.")
        return 0
    gain = target_lufs - measured
    if abs(gain) < GAIN_EPSILON_DB:
        print(f"Громкость {measured:.1f} LUFS — поправка {gain:+.1f} dB не нужна.")
        return 0
    tmp = dest.with_name(dest.stem + "-master" + dest.suffix)
    try:
        apply_gain(dest, tmp, gain)
        tmp.replace(dest)
    except (FfmpegError, OSError) as e:
        tmp.unlink(missing_ok=True)
        print(f"ВНИМАНИЕ: мастеринг не выполнен ({e}); файл оставлен как есть.")
        return 0
    print(f"Громкость: {measured:.1f} -> {target_lufs:.1f} LUFS "
          f"(поправка {gain:+.1f} dB).")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    # Без флага формат берётся ИЗ ПРОЕКТА. Раньше дефолт был «16x9», и шортс,
    # собранный из панели, выходил горизонтальным: кадры приходили 9:16, а
    # рамка оставалась 16:9, и заметить это можно было только глазами.
    ap.add_argument("--format", choices=list(COMPOSITIONS), default=None,
                    help="перебить формат проекта (по умолчанию — как в брифе)")
    ap.add_argument("--audio-only", action="store_true",
                    help="свести только звук в audio/mix.m4a (предпрослушка)")
    ap.add_argument("--dry-run", action="store_true",
                    help="напечатать монтажный лист и выйти; Node не нужен")
    ap.add_argument("--studio", action="store_true",
                    help="открыть эпизод в Remotion Studio вместо рендера")
    args = ap.parse_args(argv)

    # Чего не хватает на машине — ДО чтения проекта и до любой работы. Без
    # этой проверки отсутствующий ffmpeg вылезал трейсбеком посреди сборки, уже
    # после того, как за съёмку заплатили. `--dry-run` печатает лист и ничего
    # не запускает, поэтому его проверка не касается.
    if not args.dry_run:
        blockers = environment.problems(ROOT)
        if blockers:
            return _fail("НА ЭТОЙ МАШИНЕ НЕ ХВАТАЕТ ИНСТРУМЕНТОВ:", blockers)

    project_dir = Path(args.project)
    episode_dir = project_dir / "episodes" / args.episode

    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        return _fail("ПРОЕКТ НЕ ПРОШЁЛ ПРОВЕРКУ:", str(e).splitlines())
    fmt = args.format or montage.format_for(project)

    try:
        shots = load_shots(episode_dir / "shots.json", project_dir,
                           args.episode)
    except ShotsError as e:
        return _fail("ПЛАН СЪЁМКИ НЕ ПРОШЁЛ ПРОВЕРКУ:", str(e).splitlines())
    try:
        plan = montage.load_plan(episode_dir, shots)
    except AudioPlanError as e:
        return _fail("ПЛАН ЗВУКА НЕ ПРОШЁЛ ПРОВЕРКУ:", str(e).splitlines())

    manifest = Manifest(project_dir / "manifest.json")
    problems = montage.review_problems(manifest, args.episode, shots, plan)
    if problems:
        print("НЕ ПРИНЯТО РЕВЬЮ — монтаж заблокирован:")
        for item_id in sorted(problems):
            print(f"  - {item_id}: {problems[item_id]}")
        return 3

    try:
        edit_list = montage.build_edit_list(
            project=project, project_dir=project_dir, episode=args.episode,
            shots=shots, manifest=manifest, fmt=fmt, plan=plan,
            knowledge_dir=ROOT / "knowledge")
    except montage.MontageError as e:
        return _fail("МОНТАЖНЫЙ ЛИСТ НЕ СОБРАН:", str(e).splitlines())

    if args.dry_run:
        print(json.dumps(edit_list, ensure_ascii=False, indent=2))
        return 0

    # Лист живёт во временном файле: он бывает длинным, а командная строка
    # Windows ограничена. Каталог проекта отдаётся как --public-dir, поэтому
    # все пути внутри листа относительные и рендер видит ровно то, что можно.
    with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(edit_list, fh, ensure_ascii=False)
        props_path = Path(fh.name)

    public_dir = project_dir.resolve()
    composition = COMPOSITIONS[fmt]
    try:
        if args.studio:
            code = run_node(["remotion", "studio",
                             f"--props={props_path}",
                             f"--public-dir={public_dir}"])
            what = "Studio"
        else:
            if args.audio_only:
                dest = episode_dir / "audio" / "mix.m4a"
                extra = ["--codec=aac"]
            else:
                suffix = "" if fmt == "16x9" else f"-{fmt}"
                dest = episode_dir / "final" / f"{args.episode}{suffix}.mp4"
                extra = []
            dest.parent.mkdir(parents=True, exist_ok=True)
            code = run_node(["remotion", "render", composition,
                             str(dest.resolve()),
                             f"--props={props_path}",
                             f"--public-dir={public_dir}"] + extra)
            what = str(dest)
    finally:
        props_path.unlink(missing_ok=True)

    if code != 0:
        print(f"ОШИБКА: рендер завершился с кодом {code}.")
        return 1

    # Мастеринг громкости. Только для видеофайла: предпрослушка звука
    # (--audio-only) и Studio — рабочие инструменты, а не то, что уходит зрителю.
    if not args.studio and not args.audio_only:
        # Цель мастеринга берётся из микшера — там же, где живут громкости
        # дорожек. Два места для «как громко» разошлись бы однажды.
        target = montage.mix_settings(project)["target_lufs"]
        if target is not None:
            code = _master(dest, float(target))
            if code != 0:
                return code

    print(f"Готово: {what}")
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
