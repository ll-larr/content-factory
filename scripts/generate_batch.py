"""Батч-генерация кадров или видеоотрезков по shots.json (спека §8).

Запускать из корня репозитория:
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage storyboard
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage segments
Флаг --yes пропускает подтверждение сметы (для тестов/автоматизации).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory import higgsfield_client as hf
from factory.manifest import Manifest
from factory.models import find_card, validate_video_model
from factory.project import load_project
from factory.shots import load_shots

KNOWLEDGE_DIR = Path("knowledge")  # относительный путь — запуск из корня репо


def build_jobs(stage: str, shots: dict, project, episode_dir: Path,
               project_dir: Path) -> list[dict]:
    ep = shots["episode"]
    aspect = "9:16" if project.type == "shorts" else "16:9"
    jobs = []
    if stage == "storyboard":
        for f in shots["frames"]:
            # refs в shots.json — относительно папки проекта; CLI резолвит
            # пути от CWD, поэтому передаём абсолютные/CWD-совместимые пути.
            resolved_refs = [str(project_dir / ref) for ref in f.get("refs", [])]
            jobs.append({
                "item_id": f"{ep}/storyboard/{f['n']:03d}",
                "kind": "frame",
                "model": project.models["image"],
                "dest": episode_dir / "storyboard" / f"{f['n']:03d}.png",
                "params": {"prompt": f["prompt"], "refs": resolved_refs,
                           "aspect_ratio": aspect},
            })
    else:  # segments
        for s in shots["segments"]:
            jobs.append({
                "item_id": f"{ep}/segments/{s['n']:03d}",
                "kind": "segment",
                "model": project.models["video"],
                "dest": episode_dir / "segments" / f"{s['n']:03d}.mp4",
                "params": {
                    "prompt": s["prompt"],
                    "start_frame": str(episode_dir / "storyboard"
                                       / f"{s['start_frame']:03d}.png"),
                    "end_frame": str(episode_dir / "storyboard"
                                     / f"{s['end_frame']:03d}.png"),
                    "duration": project.segment_seconds,
                    "aspect_ratio": aspect,
                },
            })
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--stage", required=True, choices=["storyboard", "segments"])
    ap.add_argument("--yes", action="store_true",
                    help="не спрашивать подтверждение сметы")
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    project = load_project(project_dir / "project.json")
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")

    # Спека §6: валидация модели ДО траты кредитов
    if args.stage == "segments":
        card = find_card(KNOWLEDGE_DIR, project.models["video"])
        problems = validate_video_model(card, project.segment_seconds)
        if problems:
            print("МОДЕЛЬ НЕ ПРОШЛА ВАЛИДАЦИЮ — генерация не запущена:")
            for p in problems:
                print(f"  - {p}")
            return 2

    jobs = build_jobs(args.stage, shots, project, episode_dir, project_dir)
    for j in jobs:
        manifest.add(j["item_id"], kind=j["kind"])
    manifest.save()

    # Восстановление после прерванного прогона: элементы, оставшиеся в статусе
    # generating (например, после KeyboardInterrupt), возвращаются в pending,
    # чтобы следующий прогон их не потерял.
    recovered = False
    for j in jobs:
        if manifest.get(j["item_id"])["status"] == "generating":
            manifest.set_status(j["item_id"], "pending")
            recovered = True
    if recovered:
        manifest.save()

    todo = [j for j in jobs
            if manifest.get(j["item_id"])["status"] == "pending"]
    if not todo:
        print("Всё уже сгенерировано — нечего делать.")
        return 0

    # Спека §8 шаг 2: смета перед запуском
    estimates = {j["item_id"]: hf.estimate(j["model"], j["params"])
                 for j in todo}
    total = sum(estimates.values())
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.0f} кредитов "
          f"({args.stage}, модель {todo[0]['model']}).")
    if not args.yes:
        if input("Запустить? [y/N] ").strip().lower() != "y":
            print("Отменено.")
            return 1

    ok = fail = 0
    for j in todo:
        item = manifest.get(j["item_id"])
        manifest.set_status(j["item_id"], "generating")
        item["attempts"] += 1
        manifest.save()
        job_id = None
        try:
            job_id = hf.submit(j["model"], j["params"])
            result = hf.wait(job_id)
            if result.get("status") != "completed":
                raise hf.HiggsfieldError(
                    str(result.get("error", "generation failed")))
            hf.download(job_id, j["dest"])
            manifest.set_status(
                j["item_id"], "done", file=str(j["dest"]), job_id=job_id,
                credits_spent=item["credits_spent"] + estimates[j["item_id"]])
            ok += 1
        except hf.HiggsfieldError as e:
            # технический сбой -> вернуть в очередь (спека §13);
            # если job_id известен — сохраняем для соотнесения с логами Higgsfield
            extra = {"job_id": job_id} if job_id is not None else {}
            manifest.set_status(j["item_id"], "pending", **extra)
            print(f"  ! {j['item_id']}: {e}")
            fail += 1
        manifest.save()

    print(f"ИТОГ: готово {ok}, сбоев {fail}; "
          f"всего по проекту потрачено {manifest.credits_total():.0f} кредитов.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    # Защита от кириллицы в --help на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
