"""CLI пре-продакшна: состояние проекта, гейты, одобрения (спека 2026-08-02 §6).

Запускать из корня репозитория:
  python scripts/factory.py status   --project projects/pilot
  python scripts/factory.py next     --project projects/pilot
  python scripts/factory.py check    --project projects/pilot --stage script --episode ep01
  python scripts/factory.py approve  --project projects/pilot bible/idea.md
  python scripts/factory.py feedback --project projects/pilot bible/idea.md --state recorded
  python scripts/factory.py diff     --project projects/pilot bible/idea.md
  python scripts/factory.py budget   --project projects/pilot --estimate 3.0

Коды выхода: 0 успех; 1 ошибка данных; 3 гейт закрыт (в т.ч. потолок budget_usd).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.artifact import Artifact, ArtifactError, load_artifact, save_artifact
from factory.manifest import Manifest
from factory.preprod import (FEEDBACK_STATES, artifact_state, dependencies,
                             episode_ids, feedback_state, next_stage, stage_gate)

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


def _edited_since_commit(path: Path) -> bool:
    """Правил ли человек файл после того, как его закоммитил скилл этапа.

    Скилл коммитит артефакт сразу после генерации (спека §11), поэтому git и есть
    база сравнения «что написала машина» против «что стало после человека».
    """
    result = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)],
                            capture_output=True, encoding="utf-8", errors="replace")
    # Вне git-репозитория git тоже отдаёт код 1 (вместе с ошибкой в stderr), поэтому
    # одного кода возврата мало: без проверки stderr всякий артефакт вне репо
    # выглядел бы правленным.
    if result.stderr.strip():
        return False
    return result.returncode == 1


def effective_feedback(path: Path) -> str:
    """Состояние обратной связи с поправкой на факт правки.

    Поле в артефакте само по себе не знает, что человек его правил: в `pending` его
    никто не переводит. Без этой поправки `/factory-feedback` не находил бы ни одной
    строки и вся петля §11 была бы мёртвой (находка финального ревью).
    """
    state = feedback_state(path)
    if state == "none" and _edited_since_commit(path):
        return "pending"
    return state


def cmd_status(project_dir: Path) -> int:
    print(f"{'артефакт':34} {'состояние':12} feedback")
    for path in _project_artifacts(project_dir):
        rel = path.relative_to(project_dir).as_posix()
        print(f"{rel:34} {artifact_state(project_dir, path):12} "
              f"{effective_feedback(path)}")
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


def cmd_feedback(project_dir: Path, rel: str, state: str) -> int:
    if state not in FEEDBACK_STATES:
        print(f"неизвестное состояние {state!r}; известны {list(FEEDBACK_STATES)}")
        return 1
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    art = load_artifact(path)
    art.meta["feedback"] = state
    save_artifact(art)
    print(f"{rel}: feedback={state}")
    return 0


def cmd_diff(project_dir: Path, rel: str) -> int:
    """Что человек изменил с момента генерации. Базовая версия — последний коммит
    файла: скилл коммитит артефакт сразу после записи (спека §11)."""
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    result = subprocess.run(["git", "log", "-1", "--format=%H", "--", str(path)],
                            capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not result.stdout.strip():
        print(f"{rel}: нет базовой версии в git — сравнивать не с чем")
        return 0
    diff = subprocess.run(["git", "diff", "HEAD", "--", str(path)],
                          capture_output=True, encoding="utf-8", errors="replace")
    print(diff.stdout or f"{rel}: правок с момента коммита нет")
    return 0


def cmd_budget(project_dir: Path, estimate: float) -> int:
    """Влезает ли смета в остаток budget_usd. Только для autonomy: full — в
    остальных режимах трату подтверждает человек, потолок не нужен."""
    data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    if data.get("autonomy") != "full":
        print("режим не full — потолок бюджета не применяется")
        return 0
    budget = data.get("budget_usd")
    if budget is None:
        print("autonomy: full требует budget_usd в project.json")
        return 1
    manifest_path = project_dir / "manifest.json"
    spent = Manifest(manifest_path).credits_total() if manifest_path.exists() else 0.0
    remainder = float(budget) - spent
    if estimate > remainder:
        print(f"БЮДЖЕТ ИСЧЕРПАН: смета ${estimate:.4f} > остаток ${remainder:.4f} "
              f"(потолок ${float(budget):.2f}, потрачено ${spent:.4f})")
        return 3
    print(f"в бюджете: смета ${estimate:.4f}, остаток ${remainder:.4f}")
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
    fb = sub.add_parser("feedback")
    fb.add_argument("--project", required=True)
    fb.add_argument("artifact")
    fb.add_argument("--state", required=True)
    df = sub.add_parser("diff")
    df.add_argument("--project", required=True)
    df.add_argument("artifact")
    bg = sub.add_parser("budget")
    bg.add_argument("--project", required=True)
    bg.add_argument("--estimate", type=float, required=True)

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
    if args.cmd == "feedback":
        return cmd_feedback(project_dir, args.artifact, args.state)
    if args.cmd == "diff":
        return cmd_diff(project_dir, args.artifact)
    if args.cmd == "budget":
        return cmd_budget(project_dir, args.estimate)
    return cmd_approve(project_dir, args.artifact)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
