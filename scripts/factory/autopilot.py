"""Автономный режим: кто ведёт конвейер, когда человека нет.

Ведёт СЕРВЕР, а не вкладка браузера. Раньше цепочку шагов крутил JS панели, и
это ломало саму мысль режима: человек включал «автономно», закрывал ноутбук —
и конвейер вставал на первом же готовом шаге (живой прогон 2026-09-09: сценарий
написан, проверка фактов не позвана). Задача и так принадлежит серверу
(`tasks.TaskRunner`), поэтому и решение «что дальше» живёт рядом с ней.

Ручных одобрений в этом режиме НЕТ — в этом он и состоит. Одобряет сам режим,
тем же `factory.py approve --auto`, что и скилл: по файлу остаётся
`approved_by: auto`, и по проекту, прошедшему конвейер целиком, видно, что
живой человек чекпоинт не смотрел. Сгенерированные кадры и отрезки он так же
проводит через приёмку, помечая `accepted_by: auto`.

Своего порядка стадий здесь нет и быть не может: что дальше — отвечает
`preprod.next_stage`, тот же, что отвечает панели и `factory.py next`. Модуль
только исполняет.
"""
from __future__ import annotations

from pathlib import Path

from factory.manifest import Manifest, ManifestError
from factory.preprod import cli_stage, next_stage
from factory.project import ProjectError, load_project
from factory.webapp import (AWAITING_REVIEW, PAID_RUNNABLE, WebappError,
                            approve_artifact, project_overview, run_stage,
                            run_text_task)

AUTONOMOUS = "full"


def autonomy(project_dir: Path | str) -> str:
    """Кто ведёт конвейер этого проекта. Непрочитанный бриф — значит человек."""
    try:
        raw = load_project(Path(project_dir) / "project.json").raw
    except (ProjectError, OSError, ValueError):
        return "checkpoints"
    return str(raw.get("autonomy") or "checkpoints")


def step(runner, projects_root: Path | str, task: dict, *,
         repo_root: Path | str = Path(".")) -> dict | None:
    """Сделать следующий шаг за человека. None — шага не было, и это нормально.

    Зовётся после КАЖДОЙ завершённой задачи сервера. Останавливается на трёх
    вещах, и все три означают «дальше нужен человек»:

    * стадия отказала — гнать следующую по сломанному входу нечего;
    * делать больше нечего;
    * резолвер просит ТО ЖЕ САМОЕ, что только что закончилось — значит ждут
      человека (например, проверка фактов не пройдена), а повтор стадии
      переписывал бы готовое за деньги.
    """
    name = (task or {}).get("project")
    if not name or task.get("status") != "done":
        return None

    projects_root = Path(projects_root)
    project_dir = projects_root / name
    if autonomy(project_dir) != AUTONOMOUS:
        return None

    _approve_everything(project_dir, task)
    _accept_generated(project_dir, task)

    nxt = next_stage(project_dir)
    if nxt is None:
        _say(task, "автономно: делать больше нечего")
        return None

    stage, episode = nxt
    runnable = cli_stage(stage)
    paid = runnable in PAID_RUNNABLE or runnable == "render"
    # Сравниваем не только имя: у текстовой стадии `storyboard` (пишет
    # shots.json) и у платной генерации кадров одно имя запуска, и без вида
    # задачи режим считал бы вторую повтором первой и вставал ровно там, где
    # начинается съёмка.
    was_paid = task.get("kind") in ("stage", "render")
    if (paid, runnable, episode) == (was_paid, task.get("stage"),
                                     task.get("episode")):
        _say(task, f"автономно: {stage} просит того же — дальше нужен человек")
        return None

    try:
        if paid:
            return run_stage(runner, projects_root, name, episode or "", runnable)
        return run_text_task(runner, projects_root, name, runnable,
                             episode=episode, repo_root=repo_root)
    except WebappError as e:
        _say(task, f"автономно: {stage} не запустить — {e}")
        return None


def kick(runner, projects_root: Path | str, project: str, *,
         repo_root: Path | str = Path(".")) -> dict:
    """Начать автономный прогон по просьбе человека («Запустить конвейер»).

    Тот же шаг, что делается после каждой задачи, только повода нет — задача
    ещё не шла. Отдельная точка нужна потому, что стоящий проект может ждать
    ОДОБРЕНИЯ: резолвер молчит, пока артефакт не одобрен, и без первого
    одобрения прогон не начался бы вовсе.
    """
    project_dir = Path(projects_root) / project
    if autonomy(project_dir) != AUTONOMOUS:
        raise WebappError(
            "проект в ручном режиме: включи автономный тумблером или веди "
            "конвейер по шагу")
    seed = {"project": project, "status": "done", "kind": None,
            "stage": None, "episode": None, "lines": []}
    started = step(runner, projects_root, seed, repo_root=repo_root)
    return {"started": started, "lines": list(seed["lines"])}


def _approve_everything(project_dir: Path, task: dict) -> None:
    """Одобрить всё, что ждёт человека. Отказ гейта — НЕ остановка.

    Сценарий познавательного жанра нельзя одобрить, пока не пройдена проверка
    фактов, — и это не тупик, а ровно тот следующий шаг, который назовёт
    резолвер. Живой прогон 2026-09-09 встал именно здесь: панель приняла отказ
    гейта за отказ конвейера.
    """
    try:
        waiting = project_overview(project_dir)["awaiting_text"]
    except (WebappError, OSError, ValueError):
        return
    for art in waiting:
        try:
            approve_artifact(project_dir, art["path"], auto=True)
            _say(task, f"автономно одобрено: {art['path']}")
        except WebappError as e:
            _say(task, f"автономно не одобрить {art['path']}: {e}")


def _accept_generated(project_dir: Path, task: dict) -> None:
    """Провести через приёмку то, что сгенерировано и ждёт человека.

    В автономном режиме ручной приёмки нет — иначе режим встаёт на первом же
    снятом кадре. Пометка `accepted_by: auto` остаётся в манифесте: по проекту
    должно быть видно, что картинки никто живой не смотрел.
    """
    path = project_dir / "manifest.json"
    if not path.exists():
        return
    manifest = Manifest(path)
    changed = False
    for item_id, item in sorted(manifest.data.get("items", {}).items()):
        if item.get("status") != AWAITING_REVIEW:
            continue
        try:
            manifest.set_status(item_id, "done", accepted_by="auto")
        except ManifestError:
            continue
        _say(task, f"автономно принято: {item_id}")
        changed = True
    if changed:
        manifest.save()


def _say(task: dict, line: str) -> None:
    """Написать в журнал закончившейся задачи: человек читает именно его."""
    try:
        task["lines"].append(line)
    except (AttributeError, KeyError, TypeError):
        pass
