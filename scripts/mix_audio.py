"""Сведение аудиодорожки эпизода (спека фазы 2 §7, основная §11).

Запускать из корня репозитория:
  python scripts/mix_audio.py --project projects/pilot --episode ep01

Тайминг: segment+offset из audio.json; абсолютные таймкоды вычисляются по
фактическим длительностям файлов отрезков (ffprobe). Музыка приглушается
под репликами/SFX (sidechaincompress). Громкости — константы ниже.
Пути аудиофайлов — из поля file манифеста.

Коды выхода: 0 успех (или нет/пустой audio.json — без файла);
1 ошибка данных/ffmpeg; 3 аудио не принято ревью.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.audio_plan import is_empty, load_audio_plan
from factory.ffmpeg_tools import FfmpegError, probe_duration, run_ffmpeg
from factory.manifest import Manifest, ManifestError
from factory.shots import load_shots

ACCEPTED = {"done", "accepted_with_notes"}
VOICE_VOLUME = 1.0
SFX_VOLUME = 0.7
MUSIC_VOLUME = 0.35
# Приглушение музыки под репликами/SFX; параметры уточнить на smoke (Task 6)
DUCK = "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300"


def segment_timeline(shots: dict, episode_dir: Path):
    """(старт, длительность) каждого отрезка по фактическим файлам + общая длина."""
    starts: dict[int, float] = {}
    durs: dict[int, float] = {}
    t = 0.0
    for s in sorted(shots["segments"], key=lambda item: item["n"]):
        # TODO фаза 3: путь к файлу отрезка строится также в generate_batch.py
        # и assemble.py — вынести конвенцию в одно место (factory/shots.py).
        f = episode_dir / "segments" / f"{s['n']:03d}.mp4"
        if not f.exists():
            raise FfmpegError(f"Файл отрезка не найден: {f}")
        d = probe_duration(f)
        starts[s["n"]] = t
        durs[s["n"]] = d
        t += d
    return starts, durs, t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")
    ep = shots["episode"]

    plan_path = episode_dir / "audio.json"
    if not plan_path.exists():
        print(f"audio.json не найден ({plan_path}) — сведение не требуется, "
              "сборка пойдёт без звука.")
        return 0
    plan = load_audio_plan(plan_path, shots)
    if is_empty(plan):
        print("audio.json пуст — сведение не требуется, "
              "сборка пойдёт без звука.")
        return 0

    # Гейт: все аудио-единицы приняты ревью (симметрично гейтам кадров/отрезков)
    problems = {}
    for entry in plan["voice_lines"] + plan["music_cues"] + plan["sfx"]:
        item_id = f"{ep}/audio/{entry['id']}"
        try:
            status = manifest.get(item_id)["status"]
        except ManifestError:
            problems[item_id] = "не генерировался"
            continue
        if status not in ACCEPTED:
            problems[item_id] = f"статус {status}"
    if problems:
        print("АУДИО НЕ ПРИНЯТО РЕВЬЮ — сведение заблокировано:")
        for item_id in sorted(problems):
            print(f"  - {item_id}: {problems[item_id]}")
        return 3

    try:
        starts, seg_durs, total = segment_timeline(shots, episode_dir)

        def collect(list_name: str, volume: float):
            events = []
            for e in plan[list_name]:
                item_id = f"{ep}/audio/{e['id']}"
                # Гейт выше гарантирует наличие item; ManifestError здесь —
                # рассинхрон манифеста, превращаем в понятную ошибку exit 1.
                try:
                    item = manifest.get(item_id)
                except ManifestError as exc:
                    raise FfmpegError(str(exc)) from exc
                path = Path(item["file"])
                if not path.exists():
                    raise FfmpegError(
                        f"Аудиофайл из манифеста не найден: {path}")
                t = starts[e["segment"]] + e["offset"]
                dur = probe_duration(path)
                if e["offset"] + dur > seg_durs[e["segment"]] + 0.01:
                    print(f"ВНИМАНИЕ: {e['id']} ({dur:.2f}с) вылезает за "
                          f"границу отрезка {e['segment']} "
                          f"({seg_durs[e['segment']]:.2f}с).")
                events.append((path, t, volume))
            return events

        speech = collect("voice_lines", VOICE_VOLUME) + collect("sfx", SFX_VOLUME)
        music = collect("music_cues", MUSIC_VOLUME)
    except FfmpegError as e:
        print(f"ОШИБКА ffmpeg: {e}")
        return 1

    inputs: list[str] = []
    filters: list[str] = []
    labels_speech: list[str] = []
    labels_music: list[str] = []
    for idx, (path, t, vol) in enumerate(speech + music):
        inputs.extend(["-i", str(path)])
        label = f"a{idx}"
        filters.append(f"[{idx}:a]volume={vol},"
                       f"adelay={int(round(t * 1000))}:all=1[{label}]")
        (labels_speech if idx < len(speech) else labels_music).append(label)

    def add_amix(labels: list[str], out: str) -> None:
        if len(labels) == 1:
            filters.append(f"[{labels[0]}]anull[{out}]")
        else:
            filters.append(
                "".join(f"[{lb}]" for lb in labels)
                + f"amix=inputs={len(labels)}:duration=longest:normalize=0"
                + f"[{out}]")

    if speech and music:
        add_amix(labels_speech, "speech")
        add_amix(labels_music, "music")
        filters.append("[speech]asplit=2[sp1][sp2]")
        filters.append(f"[music][sp1]{DUCK}[duck]")
        filters.append("[duck][sp2]amix=inputs=2:duration=longest:"
                       "normalize=0[premix]")
    elif speech:
        add_amix(labels_speech, "premix")
    else:
        add_amix(labels_music, "premix")
    filters.append(f"[premix]atrim=0:{total:.3f},"
                   f"apad=whole_dur={total:.3f}[mix]")

    dest = episode_dir / "audio" / "mix.m4a"
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Не mix.m4a.tmp (конвенция репо): ffmpeg выбирает муксер по расширению,
    # поэтому .m4a должен остаться последним суффиксом.
    tmp = dest.with_name("mix.tmp.m4a")
    try:
        run_ffmpeg(inputs + ["-filter_complex", ";".join(filters),
                             "-map", "[mix]", "-c:a", "aac", str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1

    # Сведение успешно — финальный probe для информационной строки.
    # По образцу assemble.py:96-101: сбой probe после успешной операции
    # не роняет процесс — файл уже записан, exit 0.
    try:
        fact = probe_duration(dest)
        print(f"Сведено: {dest} ({fact:.2f}с, "
              f"реплик+SFX: {len(speech)}, музыки: {len(music)}).")
    except FfmpegError as e:
        print(f"Сведено: {dest} (не удалось проверить длительность: {e}; "
              f"реплик+SFX: {len(speech)}, музыки: {len(music)}).")
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
