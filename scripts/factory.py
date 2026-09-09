"""CLI пре-продакшна: состояние проекта, гейты, одобрения (спека 2026-08-02 §6).

Запускать из корня репозитория:
  python scripts/factory.py status   --project projects/<проект>
  python scripts/factory.py next     --project projects/<проект>
  python scripts/factory.py check    --project projects/<проект> --stage script --episode ep01
  python scripts/factory.py approve  --project projects/<проект> bible/idea.md
  python scripts/factory.py feedback --project projects/<проект> bible/idea.md --state recorded
  python scripts/factory.py diff     --project projects/<проект> bible/idea.md
  python scripts/factory.py budget   --project projects/<проект> --estimate 3.0

Коды выхода: 0 успех; 1 ошибка данных; 3 гейт закрыт (в т.ч. потолок budget_usd).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.artifact import (ArtifactError, body_sha, load_artifact,
                              save_artifact, split_frontmatter)
from factory.env import load_env
from factory.manifest import Manifest, ManifestError
from factory.models import ModelError, find_card, load_card
from factory.providers import get_provider
from factory.project import ProjectError, load_project
KNOWLEDGE_DIR = Path("knowledge")  # относительный путь — запуск из корня репо

from factory.preprod import (FEEDBACK_STATES, artifact_state,
                             dependencies, fact_check_problem, project_artifacts,
                             effective_feedback, episode_ids, feedback_state,
                             next_stage, scaffold_project, stage_problems)

# Сценарий серии: путь вида episodes/<ep>/script.md. Ровно эти артефакты
# проходят через проверку фактов, и по этому шаблону approve узнаёт серию.
_SCRIPT_REL = re.compile(r"^episodes/(?P<ep>[^/]+)/script\.md$")


def cmd_init(project_dir: Path) -> int:
    """Пустое дерево артефактов. Тем же телом пользуется мастер в панели."""
    for rel in scaffold_project(project_dir):
        print(f"создан {rel}")
    return 0


def cmd_status(project_dir: Path) -> int:
    print(f"{'артефакт':34} {'состояние':12} feedback")
    for path in project_artifacts(project_dir):
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
    """Отвечает на вопрос ЧЕЛОВЕКА «можно ли садиться за этап» — не на вопрос
    платной стадии «можно ли тратить» (тот остаётся у stage_gate/generate_batch,
    U-11). Блокер — настоящий стоп: чужой вход этапа не готов, код 3. Своя
    недоделанная работа (например, ненаписанная карточка персонажа на этапе
    characters) — не стоп, а список дел, код 0; строка про платную половину не
    выбрасывается, иначе человек, увидев код 0, пойдёт в generate_batch и
    получит код 3 — то самое расхождение «три команды, три ответа» (D-3)."""
    blockers, own_work = stage_problems(project_dir, stage, episode)
    label = f"{stage} {episode or ''}".strip()
    if blockers:
        print(f"ГЕЙТ ЗАКРЫТ — этап {stage} запускать нельзя:")
        for p in blockers:
            print(f"  - {p}")
        for p in own_work:
            print(f"  - (работа самого этапа) {p}")
        return 3
    if own_work:
        print(f"этап {label} можно вести — вот что он ещё не сделал:")
        for p in own_work:
            print(f"  - {p}")
        print("платная половина этапа недоступна, пока это не закрыто")
        return 0
    print(f"гейт открыт: {label}")
    return 0


def cmd_approve(project_dir: Path, rel: str, *, auto: bool = False) -> int:
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

    # Сценарий жанра, объявившего `fact_check: required`, не одобряется, пока
    # проверка не пройдена. Гейт стоит ИМЕННО здесь, потому что `approve` —
    # единственное место, ставящее `status: approved` (правило спеки
    # пре-продакшна): одна дверь, один замок. Код 3 — «гейт закрыт», как у
    # `check`, а не 1 «ошибка данных»: с файлом всё в порядке, не хватает работы.
    script_match = _SCRIPT_REL.match(rel.replace("\\", "/"))
    if script_match:
        problem = fact_check_problem(project_dir, script_match.group("ep"))
        if problem:
            print(f"{rel}: нельзя одобрить — факты не проверены")
            print(f"  - {problem}")
            # Лекарство печатает тот, кто знает, где стоит человек. В панели на
            # этом месте своя кнопка, и команда терминала там была бы советом
            # уйти в другое место.
            print(f"  Проверить: python scripts/text_stage.py --project "
                  f"{project_dir} --stage factcheck "
                  f"--episode {script_match.group('ep')}")
            return 3

    art.meta["status"] = "approved"
    art.meta["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds")
    # Спека §7: при autonomy auto_approve/full по файлу должно быть видно, что
    # чекпоинт не смотрел человек — иначе в режиме full по проекту не понять,
    # одобрял ли его вообще кто-нибудь живой. Отдельным полем, а не пометкой в
    # approved_at: время должно оставаться временем и разбираться как время.
    if auto:
        art.meta["approved_by"] = "auto"
    else:
        art.meta.pop("approved_by", None)
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
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError) as e:
        # Симметрично cmd_approve и cmd_status: битый артефакт — отказ с
        # объяснением, а не трейсбек. Команду запускает человек.
        print(f"{rel}: не читается — {e}")
        return 1
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
    """Влезает ли смета в остаток budget_usd.

    Потолок применяется ВЕЗДЕ, где задан, а не только при `autonomy: full`
    (решение пользователя 2026-09-09): он затем и задан, а прежнее правило
    молча не применяло его к тому, кто работает вручную. Не задан — ограничения
    нет: трату подтверждает человек, а в автономном режиме — смета всего
    прогона перед стартом.
    """
    data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    budget = data.get("budget_usd")
    if budget is None:
        print("потолок бюджета не задан (budget_usd) — ограничения нет")
        return 0
    manifest_path = project_dir / "manifest.json"
    spent = Manifest(manifest_path).credits_total() if manifest_path.exists() else 0.0
    remainder = float(budget) - spent
    if estimate > remainder:
        print(f"БЮДЖЕТ ИСЧЕРПАН: смета ${estimate:.4f} > остаток ${remainder:.4f} "
              f"(потолок ${float(budget):.4f}, потрачено ${spent:.4f})")
        return 3
    print(f"в бюджете: смета ${estimate:.4f}, остаток ${remainder:.4f}")
    return 0


# Роли моделей и каталоги карточек. Роль -> (папка knowledge, тип карточки).
MODEL_ROLES = {
    "image": ("images", "image"),
    "video": ("video", "video"),
    "audio.tts": ("audio", "audio"),
    "audio.sfx": ("audio", "audio"),
    "audio.music": ("audio", "audio"),
    "audio.foley": ("audio", "audio"),
    "audio.lipsync": ("audio", "audio"),
}


def _card_price(card: dict) -> str:
    """Цена карточки одной строкой для списка выбора.

    Карточка с закомментированным блоком провайдеров цены не имеет — так и
    пишем. Это не дефект: закомментировано ровно то, что не подтверждено живой
    генерацией, и показывать каталожную догадку как цену значило бы врать.
    """
    providers = card.get("providers") or {}
    parts = []
    for name, pv in sorted(providers.items()):
        entries = pv.get("tiers", {"": pv}) if isinstance(pv, dict) else {}
        for tier, entry in sorted(entries.items()):
            # `or` здесь был бы ошибкой: бесплатная модель (цена 0) провалилась
            # бы в следующее поле и показалась бы как «цены нет».
            price = entry.get("usd_per_image")
            per_image = price is not None
            if price is None:
                price = entry.get("usd_per_sec")
            if price is None:
                continue
            # usd_per_image у видео означает плоскую цену за ГЕНЕРАЦИЮ, а не за
            # кадр: у veo это $3.2 за клип. Подпись «за кадр» на видео читалась
            # бы как цена за один кадр из двадцати четырёх в секунде.
            if per_image:
                unit = "за генерацию" if card.get("type") == "video" else "за кадр"
            else:
                unit = "за секунду"
            label = f"{name}/{tier}" if tier else name
            parts.append(f"{label} ${price} {unit}")
    return "; ".join(parts) or "цены нет (провайдер не подтверждён)"


def cmd_models(project_dir: Path, set_expr: str | None) -> int:
    """Показать доступные модели с ценами или записать выбор в project.json."""
    project_file = project_dir / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))

    if set_expr:
        if "=" not in set_expr:
            print(f"ожидается роль=модель, получено: {set_expr!r}")
            return 1
        role, model = (s.strip() for s in set_expr.split("=", 1))
        if role not in MODEL_ROLES:
            print(f"неизвестная роль {role!r}; известны: {sorted(MODEL_ROLES)}")
            return 1
        try:
            card = find_card(KNOWLEDGE_DIR, model)
        except ModelError as e:
            print(str(e))
            return 1
        # Скелет не должен становиться выбором: гейт трат отобьёт его на платной
        # стадии, но человек узнает об этом, уже дойдя до неё.
        if card.get("status") == "skeleton":
            print(f"{model}: карточка skeleton — возможности и цена не "
                  f"подтверждены живой генерацией, выбирать нельзя")
            return 1
        block = data.setdefault("models", {})
        if "." in role:
            outer, inner = role.split(".", 1)
            entry = block.setdefault(outer, {}).get(inner)
        else:
            outer, inner, entry = role, None, block.get(role)
        provider = entry.get("provider") if isinstance(entry, dict) else None
        new = {"model": model}
        if provider:
            new["provider"] = provider
        if inner:
            block[outer][inner] = new
        else:
            block[outer] = new
        project_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"{role} = {model}")
        return 0

    for role, (folder, _kind) in MODEL_ROLES.items():
        if "." in role:
            outer, inner = role.split(".", 1)
            current = (data.get("models", {}).get(outer, {}) or {}).get(inner)
        else:
            current = data.get("models", {}).get(role)
        current_name = current.get("model") if isinstance(current, dict) else current
        print(f"\n{role}: сейчас {current_name or '—'}")
        folder_path = KNOWLEDGE_DIR / folder
        if not folder_path.exists():
            continue
        for path in sorted(folder_path.glob("*.md")):
            if path.name.startswith("_"):
                continue
            try:
                card = load_card(path)
            except (ModelError, OSError, ValueError):
                continue
            status = card.get("status")
            # Статус виден в списке: verified молчит, остальные называют себя.
            # «catalog» значит «цена из каталога провайдера, живой генерации не
            # было» — человек должен видеть это в момент выбора, а не узнавать
            # из расхождения сметы со списанием.
            mark = "  " if status == "verified" else f"  {status} "
            here = " <— выбрана" if card.get("id") == current_name else ""
            print(f"  {mark}{card.get('id'):24s} {_card_price(card)}{here}")
    return 0


def cmd_estimate(project_dir: Path, episode: str) -> int:
    """Одна смета на весь остаток эпизода — то, что видит человек на чекпоинте.

    Раньше смета печаталась перед КАЖДОЙ платной стадией по отдельности, и общей
    цены серии человек не видел никогда: он соглашался четыре раза на четыре
    куска. Здесь стадии складываются, а уже принятое не считается — платить
    второй раз за принятый кадр не придётся.

    Считает `factory.estimate`, здесь только печать: те же числа показывает
    панель, и две слегка разные сметы однажды разошлись бы в ответе.
    """
    from factory.estimate import EstimateError, episode_estimate

    try:
        data = episode_estimate(project_dir, episode, KNOWLEDGE_DIR)
    except EstimateError as e:
        print(e)
        return 1

    for problem in data["problems"]:
        print(f"  ! {problem}")

    print(f"СМЕТА ОСТАТКА {episode} ({project_dir.name}):")
    for row in data["rows"]:
        print(f"  {row['stage']:12s} {row['count']:3d} шт  ${row['cost']:.4f}")
    if not data["rows"]:
        print("  всё сделано — платить не за что")
    print(f"  {'ИТОГО':12s}      ${data['total']:.4f}")

    budget = data["budget"]
    if budget is not None:
        print(f"  потрачено ${budget['spent']:.4f} из ${budget['limit']:.4f}; "
              f"после этой сметы останется "
              f"${budget['left'] - data['total']:.4f}")
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
    approve.add_argument(
        "--auto", action="store_true",
        help="одобрение принял драйвер, а не человек (autonomy: auto_approve/full)")
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
    es = sub.add_parser("estimate")
    es.add_argument("--project", required=True)
    es.add_argument("--episode", required=True)
    md = sub.add_parser("models")
    md.add_argument("--project", required=True)
    md.add_argument("--set", dest="set_expr",
                    help="записать выбор: роль=модель (напр. image=seedream_v5_pro)")

    args = ap.parse_args(argv)
    # Ключи из .env рядом с корнем: на чужой машине это единственный способ
    # задать их, не воюя с системными переменными окружения.
    load_env(Path(__file__).resolve().parent.parent)
    project_dir = Path(args.project)
    if not (project_dir / "project.json").exists():
        print(f"нет {project_dir / 'project.json'}")
        return 1

    # Непригодный project.json — ошибка данных (код 1), а не трейсбек: из него
    # растут и состав эпизодов (episode_ids), и гейты, поэтому уронить может почти
    # любую команду. Команду запускает человек, и ему нужно понять, что чинить.
    try:
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
        if args.cmd == "estimate":
            return cmd_estimate(project_dir, args.episode)
        if args.cmd == "models":
            return cmd_models(project_dir, args.set_expr)
        if args.cmd == "budget":
            return cmd_budget(project_dir, args.estimate)
        return cmd_approve(project_dir, args.artifact, auto=args.auto)
    except ProjectError as e:
        print(f"{project_dir / 'project.json'}: {e}")
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
