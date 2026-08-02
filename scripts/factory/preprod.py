"""Состояние артефактов и гейты первой половины конвейера (спека 2026-08-02 §5).

Одобрение живёт во frontmatter артефакта вместе с хешом тела и хешами зависимостей,
поэтому правка утверждённого текста не проходит молча.
"""
from __future__ import annotations

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
