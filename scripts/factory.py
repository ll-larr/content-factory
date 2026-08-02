"""CLI пре-продакшна: состояние проекта, гейты, одобрения (спека 2026-08-02 §6).

Запускать из корня репозитория:
  python scripts/factory.py status  --project projects/pilot
  python scripts/factory.py next    --project projects/pilot
  python scripts/factory.py check   --project projects/pilot --stage script --episode ep01
  python scripts/factory.py approve --project projects/pilot bible/idea.md

Коды выхода: 0 успех; 1 ошибка данных; 3 гейт закрыт.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.artifact import Artifact, ArtifactError, load_artifact, save_artifact
from factory.preprod import (artifact_state, dependencies, episode_ids,
                             next_stage, stage_gate)

# Артефакты, которые создаёт init. Персонажи не скаффолдятся: их состав известен
# только после сценария.
SCAFFOLD = {
    "bible/idea.md": "idea",
    "bible/season-arc.md": "season-arc",
    "bible/style-guide.md": "style-guide",
}


def _project_artifacts(project_dir: Path) -> list[Path]:
    paths = [project_dir / rel for rel in SCAFFOLD]
    paths += sorted((project_dir / "bible" / "characters").glob("*.md"))
    paths += sorted((project_dir / "episodes").glob("*/script.md"))
    research = project_dir / "research.md"
    if research.exists():
        paths.append(research)
    return paths


def cmd_init(project_dir: Path) -> int:
    for rel, kind in SCAFFOLD.items():
        path = project_dir / rel
        if path.exists():
            continue          # идемпотентность: написанное не затираем
        save_artifact(Artifact(path=path, meta={"kind": kind, "status": "draft"},
                               body=""))
        print(f"создан {rel}")
    for ep in episode_ids(project_dir):
        (project_dir / "episodes" / ep).mkdir(parents=True, exist_ok=True)
    return 0


def cmd_status(project_dir: Path) -> int:
    for path in _project_artifacts(project_dir):
        rel = path.relative_to(project_dir).as_posix()
        print(f"{rel:34} {artifact_state(project_dir, path)}")
    return 0


def cmd_next(project_dir: Path) -> int:
    nxt = next_stage(project_dir)
    if nxt is None:
        print("всё закрыто — следующего шага нет")
        return 0
    stage, episode = nxt
    print(f"{stage} {episode or ''}".strip())
    return 0


def cmd_check(project_dir: Path, stage: str, episode: str | None) -> int:
    problems = stage_gate(project_dir, stage, episode)
    if not problems:
        print(f"гейт открыт: {stage} {episode or ''}".strip())
        return 0
    print(f"ГЕЙТ ЗАКРЫТ — этап {stage} запускать нельзя:")
    for p in problems:
        print(f"  - {p}")
    return 3


def cmd_approve(project_dir: Path, rel: str) -> int:
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError) as e:
        # Отказ, а не трейсбек: команду запускает человек, и ему нужно понять, что
        # чинить. Симметрично обработке нечитаемой зависимости ниже.
        print(f"{rel}: не читается — {e}")
        return 1
    if not art.body.strip():
        print(f"{rel}: тело пустое — нечего одобрять")
        return 1
    art.meta["status"] = "approved"
    art.meta["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds")
    art.meta["content_sha"] = art.sha
    # dependencies() возвращает ОБЪЯВЛЕННЫЕ зависимости, в том числе несуществующие:
    # это сознательно, иначе порядок одобрения молча ломал бы depends_on. Здесь же
    # несуществующая зависимость — повод отказать: одобрять артефакт, основание
    # которого ещё не написано, бессмысленно (находка ревью задачи 2).
    deps = []
    missing = []
    unreadable = []
    for dep in dependencies(project_dir, art):
        rel_dep = dep.relative_to(project_dir).as_posix()
        if not dep.exists():
            missing.append(rel_dep)
            continue
        try:
            deps.append({"path": rel_dep, "sha": load_artifact(dep).sha})
        except (ArtifactError, OSError):
            # Зависимость есть на диске, но не разбирается (битый frontmatter) —
            # ровно та же логика, что artifact_state применяет к чужому stale_deps:
            # подтвердить, что основание не менялось, мы не можем, значит не вправе
            # это одобрять. Без этой ветки load_artifact(dep) уронил бы весь CLI
            # необработанным ArtifactError вместо кода 1 (найдено при самопроверке
            # задачи 4 — .superpowers/sdd/pp-task-4-report.md).
            unreadable.append(rel_dep)
    if missing or unreadable:
        print(f"{rel}: нельзя одобрить — проблемы с зависимостями:")
        for m in missing:
            print(f"  - {m}: не существует")
        for u in unreadable:
            print(f"  - {u}: не разбирается (битый frontmatter)")
        return 1
    if deps:
        art.meta["depends_on"] = deps
    save_artifact(art)
    print(f"одобрено: {rel}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "status", "next"):
        sub.add_parser(name).add_argument("--project", required=True)
    check = sub.add_parser("check")
    check.add_argument("--project", required=True)
    check.add_argument("--stage", required=True)
    check.add_argument("--episode")
    approve = sub.add_parser("approve")
    approve.add_argument("--project", required=True)
    approve.add_argument("artifact")

    args = ap.parse_args(argv)
    project_dir = Path(args.project)
    if not (project_dir / "project.json").exists():
        print(f"нет {project_dir / 'project.json'}")
        return 1

    if args.cmd == "init":
        return cmd_init(project_dir)
    if args.cmd == "status":
        return cmd_status(project_dir)
    if args.cmd == "next":
        return cmd_next(project_dir)
    if args.cmd == "check":
        return cmd_check(project_dir, args.stage, args.episode)
    return cmd_approve(project_dir, args.artifact)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
