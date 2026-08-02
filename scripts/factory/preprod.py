"""Состояние артефактов и гейты первой половины конвейера (спека 2026-08-02 §5).

Одобрение живёт во frontmatter артефакта вместе с хешом тела и хешами зависимостей,
поэтому правка утверждённого текста не проходит молча.
"""
from __future__ import annotations

import json
from pathlib import Path

from factory.artifact import Artifact, ArtifactError, load_artifact

# Карта зависимостей по kind — фиксированная, а не свободный список: иначе два
# запуска approve дали бы разный depends_on и проверка устаревания стала бы
# недетерминированной (спека §4).
DEPENDS_ON: dict[str, list[str]] = {
    "research": [],
    "idea": [],
    "season-arc": ["bible/idea.md"],
    "style-guide": ["bible/idea.md"],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "character": ["bible/idea.md", "bible/style-guide.md"],
}


def dependencies(project_dir: Path, art: Artifact) -> list[Path]:
    """Файлы, от которых артефакт зависит. Для персонажа к статическому списку
    добавляются сценарии, где он упомянут: правка такого сценария меняет то, каким
    персонаж должен быть.

    Список статических путей отдаётся как есть, даже если файл ещё не создан:
    это ожидаемые зависимости по карте DEPENDS_ON, а не проверка «что уже готово».
    Отфильтровывать несуществующее тут не нужно и вредно — например, approve
    сценария должен видеть bible/idea.md среди его зависимостей независимо от
    порядка, в котором артефакты создаются. Сценарии из glob по построению уже
    существуют, дополнительная фильтрация им не требуется."""
    project_dir = Path(project_dir)
    kind = art.meta.get("kind")
    deps = [project_dir / rel for rel in DEPENDS_ON.get(kind, [])]
    if kind == "character":
        name = art.meta.get("name") or art.path.stem
        for script in sorted((project_dir / "episodes").glob("*/script.md")):
            try:
                body = load_artifact(script).body
            except (ArtifactError, OSError):
                # Сценарий существует, но не разбирается (например нет frontmatter) —
                # понять, упомянут ли в нём персонаж, невозможно, поэтому молча
                # пропускаем. Сам этот сценарий всё равно будет отбит гейтом
                # собственного этапа, когда до него дойдут напрямую.
                continue
            if name in body:
                deps.append(script)
    return deps


def artifact_state(project_dir: Path, path: Path) -> str:
    """missing | draft | approved | stale_self | stale_deps."""
    project_dir, path = Path(project_dir), Path(path)
    if not path.exists():
        return "missing"
    art = load_artifact(path)
    if art.meta.get("status") != "approved":
        return "draft"
    if art.meta.get("content_sha") != art.sha:
        return "stale_self"
    for dep in art.meta.get("depends_on") or []:
        dep_path = project_dir / dep["path"]
        if not dep_path.exists():
            return "stale_deps"
        try:
            dep_sha = load_artifact(dep_path).sha
        except (ArtifactError, OSError):
            # Зависимость есть на диске, но не разбирается (битый/чужой frontmatter) —
            # у контракта artifact_state нет состояния "ошибка", а подтвердить, что
            # основание не изменилось, мы не можем. Значит не вправе звать это
            # approved: та же логика, что и для удалённой зависимости выше, поэтому
            # тот же исход — stale_deps, а не отдельное "broken".
            return "stale_deps"
        if dep_sha != dep["sha"]:
            return "stale_deps"
    return "approved"


STAGES = ("research", "story", "script", "characters", "storyboard")

# Что каждый этап требует одобренным. {ep} подставляется номером эпизода.
STAGE_REQUIRES: dict[str, list[str]] = {
    "research": [],
    "story": [],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "characters": ["episodes/{ep}/script.md"],
    "storyboard": ["episodes/{ep}/script.md", "bible/style-guide.md"],
}

_STATE_MESSAGE = {
    "missing": "не существует",
    "draft": "не одобрен (status: draft)",
    "stale_self": "изменён после одобрения — перечитай и одобри заново",
    "stale_deps": "устарел: изменился файл, на который он опирался",
}


def episode_ids(project_dir: Path) -> list[str]:
    """ep01..epNN по полю episodes из project.json; для типов без серий — ['ep01']."""
    data = json.loads((Path(project_dir) / "project.json").read_text(encoding="utf-8"))
    count = int(data.get("episodes", 1) or 1)
    return [f"ep{i:02d}" for i in range(1, count + 1)]


def stage_gate(project_dir: Path, stage: str, episode: str | None = None) -> list[str]:
    """Пустой список = этап можно запускать. Иначе — по строке на каждую причину."""
    project_dir = Path(project_dir)
    if stage not in STAGES:
        return [f"неизвестный этап {stage!r}; известны {list(STAGES)}"]

    problems: list[str] = []
    for template in STAGE_REQUIRES[stage]:
        if "{ep}" in template and episode is None:
            problems.append(f"этап {stage} требует --episode")
            continue
        rel = template.format(ep=episode)
        state = artifact_state(project_dir, project_dir / rel)
        if state != "approved":
            problems.append(f"{rel}: {_STATE_MESSAGE[state]}")

    if stage == "storyboard":
        chars = sorted((project_dir / "bible" / "characters").glob("*.md"))
        if not chars:
            problems.append("bible/characters/: нет ни одной карточки персонажа")
        for card in chars:
            state = artifact_state(project_dir, card)
            if state != "approved":
                rel = card.relative_to(project_dir).as_posix()
                problems.append(f"{rel}: {_STATE_MESSAGE[state]}")
    return problems


def next_stage(project_dir: Path) -> tuple[str, str | None] | None:
    """Первый незакрытый шаг. Порядок: story, затем эпизоды ПО ПОРЯДКУ, в каждом
    script → characters → storyboard (спека §7: автономный режим идёт по всем)."""
    project_dir = Path(project_dir)
    story_done = all(
        artifact_state(project_dir, project_dir / rel) == "approved"
        for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"))
    if not story_done:
        return ("story", None)

    for ep in episode_ids(project_dir):
        if artifact_state(project_dir, project_dir / f"episodes/{ep}/script.md") != "approved":
            return ("script", ep)
        chars = sorted((project_dir / "bible" / "characters").glob("*.md"))
        if not chars or any(artifact_state(project_dir, c) != "approved" for c in chars):
            return ("characters", ep)
        if not (project_dir / "episodes" / ep / "shots.json").exists():
            return ("storyboard", ep)
    return None
