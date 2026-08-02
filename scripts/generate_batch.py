"""Батч-генерация референсов персонажей, кадров или видеоотрезков по shots.json
(спека §8; провайдеры — FINAL §5; стадия characters — спека 2026-08-02 §9).

Запускать из корня репозитория:
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage characters
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage storyboard
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage segments
Флаг --yes пропускает подтверждение сметы (для тестов/автоматизации).
Референсы персонажей и кадры идут через image-провайдера проекта, отрезки — через
video-провайдера (оба задаются в project.json; дефолт — по типу контента, FINAL §4).
Успешные генерации получают статус generated и ждут ревью (scripts/review.py).

Коды выхода: 0 успех; 1 сбои/отмена; 2 модель не прошла валидацию или промпт
кадра не прошёл гейт консистентности (§10: {{style}}/{{char:...}}/refs);
3 стадия заблокирована — закрыт гейт пре-продакшна (§5: карточка персонажа не
одобрена и т.п.), кадры не приняты ревью (segments) или референс персонажа не
принят ревью (storyboard).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.ffmpeg_tools import FfmpegError, ensure_png
from factory.manifest import Manifest, ManifestError
from factory.models import find_card, validate_image_model, validate_video_model
from factory.preprod import episode_cast, stage_gate
from factory.project import load_project
from factory.prompts import canonical_block, expand_prompt, prompt_problems
from factory.providers import get_provider
from factory.providers.base import ProviderError
from factory.shots import frame_path, load_shots, segment_path

_PLACEHOLDER_ANY = re.compile(r"\{\{[^}]*\}\}")

KNOWLEDGE_DIR = Path("knowledge")  # относительный путь — запуск из корня репо


def _validation_gate(problems: list[str]) -> int:
    """Единый вывод + код 2 для всех гейтов трат ДО сметы: и валидация карточки
    (validate_video_model/validate_image_model), и провайдерский хук
    (preflight_problems — ревью-находка: смета не должна обещать цену, которую
    submit не может выполнить) используют один и тот же формат сообщения —
    пользователь видит одинаковую картину независимо от того, какая именно
    проверка остановила прогон."""
    print("МОДЕЛЬ НЕ ПРОШЛА ВАЛИДАЦИЮ — генерация не запущена:")
    for p in problems:
        print(f"  - {p}")
    return 2


def build_jobs(stage: str, shots: dict | None, project, episode_dir: Path,
               project_dir: Path) -> list[dict]:
    aspect = "9:16" if project.type == "shorts" else "16:9"
    jobs = []
    if stage == "characters":
        # Референсы — по составу ИМЕННО этой серии (episode_cast), а не по всем
        # карточкам bible/characters/: карточка персонажа из другой серии не
        # должна ни блокировать эту, ни оплачиваться повторно (поправка 2 задачи
        # 6; та же логика, что уже применена в preprod._cast_problems).
        # shots для этой стадии не нужен и не загружается (episode здесь берём из
        # имени папки эпизода) — этап 5 (characters) в спеке §8 предшествует
        # этапу 6 (storyboard), который только и производит shots.json, поэтому
        # на момент запуска этой стадии файла может ещё не существовать.
        for name in episode_cast(project_dir, episode_dir.name):
            card = project_dir / "bible" / "characters" / f"{name}.md"
            appearance = canonical_block(card, "appearance")
            jobs.append({
                "item_id": f"bible/characters/{name}",
                "kind": "character_ref",
                "model": project.image_model,
                "dest": card.with_name(f"{name}-ref.png"),
                "params": {
                    "prompt": f"character sheet, three angles, neutral background. "
                              f"{appearance}",
                    "refs": [], "aspect_ratio": aspect,
                    "resolution": project.resolution, "tier": project.image_tier,
                },
            })
        return jobs

    ep = shots["episode"]
    if stage == "storyboard":
        for f in shots["frames"]:
            # refs в shots.json — относительно папки проекта; передаём
            # абсолютные/CWD-совместимые пути.
            resolved_refs = [str(project_dir / ref) for ref in f.get("refs", [])]
            expanded = expand_prompt(f["prompt"], project_dir)
            jobs.append({
                "item_id": f"{ep}/storyboard/{f['n']:03d}",
                "kind": "frame",
                "model": project.image_model,
                "dest": frame_path(episode_dir, f["n"]),
                "params": {"prompt": expanded, "refs": resolved_refs,
                           "aspect_ratio": aspect, "resolution": project.resolution,
                           "tier": project.image_tier},
            })
    else:  # segments
        for s in shots["segments"]:
            jobs.append({
                "item_id": f"{ep}/segments/{s['n']:03d}",
                "kind": "segment",
                "model": project.video_model,
                "dest": segment_path(episode_dir, s["n"]),
                "params": {
                    "prompt": s["prompt"],
                    "start_frame": str(frame_path(episode_dir, s["start_frame"])),
                    "end_frame": str(frame_path(episode_dir, s["end_frame"])),
                    "duration": project.segment_seconds,
                    "aspect_ratio": aspect,
                    "resolution": project.resolution,
                    "tier": project.video_tier,
                },
            })
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--stage", required=True,
                    choices=["storyboard", "segments", "characters"])
    ap.add_argument("--yes", action="store_true",
                    help="не спрашивать подтверждение сметы")
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    project = load_project(project_dir / "project.json")
    episode_dir = project_dir / "episodes" / args.episode
    manifest = Manifest(project_dir / "manifest.json")

    aspect = "9:16" if project.type == "shorts" else "16:9"

    # shots.json грузим только там, где он нужен: этап characters (спека §8)
    # предшествует этапу storyboard, который его производит, — на момент запуска
    # characters файла может ещё не существовать.
    shots = None
    if args.stage in ("storyboard", "segments"):
        shots = load_shots(episode_dir / "shots.json", project_dir)

    if args.stage == "segments":
        provider_name = project.video_provider
        # Спека §6: валидация модели ПОД ВЫБРАННОГО провайдера ДО трат
        card = find_card(KNOWLEDGE_DIR, project.video_model)
        problems = validate_video_model(card, project.segment_seconds, provider_name)
        if problems:
            return _validation_gate(problems)

        # Ревью-находка: смета не должна обещать цену, которую submit не
        # выполнит (напр. Runware не умеет resolution проекта) — провайдерский
        # хук проверяется здесь же, ДО сметы, тем же кодом 2.
        provider = get_provider(provider_name, KNOWLEDGE_DIR)
        problems = provider.preflight_problems(project.video_model, {
            "resolution": project.resolution, "aspect_ratio": aspect,
            "duration": project.segment_seconds, "tier": project.video_tier,
        })
        if problems:
            return _validation_gate(problems)

        # Чекпоинт ревью (спека ревью §4.3): отрезки строятся только на
        # принятых кадрах — done или accepted_with_notes.
        accepted = {"done", "accepted_with_notes"}
        frame_problems = {}
        for s in shots["segments"]:
            for n in (s["start_frame"], s["end_frame"]):
                frame_id = f"{shots['episode']}/storyboard/{n:03d}"
                if frame_id in frame_problems:
                    continue
                try:
                    status = manifest.get(frame_id)["status"]
                except ManifestError:
                    frame_problems[frame_id] = "не генерировался"
                    continue
                if status not in accepted:
                    frame_problems[frame_id] = f"статус {status}"
        if frame_problems:
            print("КАДРЫ НЕ ПРИНЯТЫ РЕВЬЮ — стадия segments заблокирована:")
            for frame_id in sorted(frame_problems):
                print(f"  - {frame_id}: {frame_problems[frame_id]}")
            return 3

        # Промпты движения плейсхолдеры НЕ разворачивают: композицию задают кадры,
        # описывать в отрезке внешность заново незачем. Но раз не разворачивают —
        # случайно вписанный {{style}} уехал бы провайдеру буквально и оплатился
        # мусором. Отбиваем до сметы (ревью-находка задачи 5).
        stray = []
        for s in shots["segments"]:
            for junk in _PLACEHOLDER_ANY.findall(s["prompt"]):
                stray.append(f"отрезок {s['n']:03d}: {junk!r}")
        if stray:
            print("ПЛЕЙСХОЛДЕРЫ В ПРОМПТЕ ДВИЖЕНИЯ — генерация не запущена "
                  "(отрезки их не разворачивают):")
            for p in stray:
                print(f"  - {p}")
            return 2
    else:
        provider_name = project.image_provider

        if args.stage == "characters":
            # Гейт первой половины (спека §5/§9): характеры генерируются только
            # для одобренного (текстово) состава серии — stage_gate сам смотрит
            # состав через episode_cast, а не на то, что уже лежит в
            # bible/characters/ (поправка 1 задачи 6).
            problems = stage_gate(project_dir, "characters", args.episode)
            if problems:
                print("ГЕЙТ ЗАКРЫТ — стадия characters недоступна:")
                for p in problems:
                    print(f"  - {p}")
                return 3

        if args.stage == "storyboard":
            # Чекпоинт консистентности (спека §9): раскадровка не стартует, пока
            # референс каждого персонажа СОСТАВА ЭТОЙ СЕРИИ (episode_cast, а не
            # все карточки bible/characters/ — поправка 2 задачи 6) не принят
            # ревью — done или accepted_with_notes.
            accepted = {"done", "accepted_with_notes"}
            not_ready = []
            for name in episode_cast(project_dir, args.episode):
                item_id = f"bible/characters/{name}"
                try:
                    status = manifest.get(item_id)["status"]
                except ManifestError:
                    not_ready.append(f"{item_id}: референс не генерировался")
                    continue
                if status not in accepted:
                    not_ready.append(f"{item_id}: статус {status}")
            if not_ready:
                print("РЕФЕРЕНСЫ ПЕРСОНАЖЕЙ НЕ ПРИНЯТЫ — стадия storyboard "
                      "заблокирована:")
                for p in not_ready:
                    print(f"  - {p}")
                return 3

        # Гейт трат раскадровки (симметрично video): валидация image-модели под
        # выбранного провайдера ДО сметы — skeleton/не-тот-провайдер → код 2.
        card = find_card(KNOWLEDGE_DIR, project.image_model)
        problems = validate_image_model(card, provider_name)
        if problems:
            return _validation_gate(problems)

        # Ревью-находка, симметрично segments: провайдерский хук ДО сметы.
        provider = get_provider(provider_name, KNOWLEDGE_DIR)
        problems = provider.preflight_problems(project.image_model, {
            "resolution": project.resolution, "aspect_ratio": aspect,
            "tier": project.image_tier,
        })
        if problems:
            return _validation_gate(problems)

        # Гейт консистентности (спека §10): негодный промпт — {{style}} не
        # объявлен, {{char:...}} без карточки/одобрения/референса, неизвестный
        # плейсхолдер — отбиваем ДО сметы. Иначе кадр без референса персонажа
        # оплатится и придёт неконсистентным.
        if args.stage == "storyboard":
            bad = []
            for f in shots["frames"]:
                for problem in prompt_problems(f["prompt"], project_dir,
                                               f.get("refs", [])):
                    bad.append(f"кадр {f['n']:03d}: {problem}")
            if bad:
                print("ПРОМПТЫ НЕ ПРОШЛИ ПРОВЕРКУ — генерация не запущена:")
                for p in bad:
                    print(f"  - {p}")
                return 2

    jobs = build_jobs(args.stage, shots, project, episode_dir, project_dir)
    for j in jobs:
        manifest.add(j["item_id"], kind=j["kind"])
    manifest.save()

    # Восстановление после прерванного прогона: generating → pending.
    recovered = False
    for j in jobs:
        if manifest.get(j["item_id"])["status"] == "generating":
            manifest.set_status(j["item_id"], "pending")
            recovered = True
    if recovered:
        manifest.save()

    # Цикл ревью (спека ревью §4.2): отклонённые — на перегенерацию, пока не
    # исчерпан лимит max_rejections; дальше — решение человека (review.py requeue).
    blocked = []
    requeued = False
    for j in jobs:
        item = manifest.get(j["item_id"])
        if item["status"] != "rejected":
            continue
        if item.get("reject_count", 0) < project.max_rejections:
            manifest.set_status(j["item_id"], "pending")
            requeued = True
        else:
            blocked.append(j["item_id"])
    if requeued:
        manifest.save()
    if blocked:
        print(f"ЛИМИТ ОТКЛОНЕНИЙ ИСЧЕРПАН (max_rejections="
              f"{project.max_rejections}) — требуется решение человека:")
        for item_id in blocked:
            it = manifest.get(item_id)
            print(f"  - {item_id}: reject_count={it.get('reject_count', 0)}, "
                  f"последняя причина: {it.get('reject_reason')}")

    todo = [j for j in jobs
            if manifest.get(j["item_id"])["status"] == "pending"]
    if not todo:
        awaiting = [j["item_id"] for j in jobs
                    if manifest.get(j["item_id"])["status"] == "generated"]
        if awaiting:
            print(f"Генерация не требуется; {len(awaiting)} единиц ждут ревью "
                  f"(scripts/review.py):")
            for item_id in awaiting:
                print(f"  - {item_id}")
        else:
            print("Всё уже сгенерировано — нечего делать.")
        return 0

    # provider уже создан выше (рядом с preflight-хуком) — переиспользуем.

    # Спека §8 шаг 2: смета перед запуском (бесплатно, до трат)
    estimates = {j["item_id"]: provider.estimate(j["model"], j["params"])
                 for j in todo}
    total = sum(estimates.values())
    models_used = ", ".join(sorted({j["model"] for j in todo}))
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.4f} {provider.unit} "
          f"({args.stage}, провайдер {provider_name}, модели: {models_used}).")
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
            job_id = provider.submit(j["model"], j["params"])
            provider.wait(job_id)
            provider.download(job_id, j["dest"])
            if j["kind"] in ("frame", "character_ref"):
                # провайдер может отдать JPEG под именем .png — нормализуем
                # (референс персонажа — такой же скачанный PNG-файл, как кадр)
                ensure_png(j["dest"])
            manifest.set_status(
                j["item_id"], "generated", file=str(j["dest"]), job_id=job_id,
                prompt_sent=j["params"].get("prompt"),
                credits_spent=item["credits_spent"] + estimates[j["item_id"]])
            ok += 1
        except (ProviderError, FfmpegError) as e:
            # технический сбой (провайдер или конвертация ensure_png) -> вернуть
            # в очередь (спека §13); если job_id известен — сохраняем для
            # соотнесения с логами провайдера
            extra = {"job_id": job_id} if job_id is not None else {}
            manifest.set_status(j["item_id"], "pending", **extra)
            print(f"  ! {j['item_id']}: {e}")
            fail += 1
        manifest.save()

    print(f"ИТОГ: сгенерировано {ok} (ждут ревью), сбоев {fail}; "
          f"всего по проекту потрачено {manifest.credits_total():.4f} {provider.unit}.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    # Защита от кириллицы в --help на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
