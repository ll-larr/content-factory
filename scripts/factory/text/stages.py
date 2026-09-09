"""Текстовые стадии: что читаем, что пишем и каким промптом просим.

Методика стадии НЕ переписывается сюда. Системным промптом становится тело
скилла (`.claude/skills/factory-*/SKILL.md` без frontmatter) плюс карточка жанра:
скилл остаётся единственным местом, где написано, как работает стадия, и его
правка меняет оба движка сразу — и агентский путь, и путь по ключу.

Здесь только доставка: собрать промпт, разобрать ответ, разложить файлы. Ни одного
решения о том, каким должен быть сценарий, в этом модуле нет.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from factory.artifact import ArtifactError, split_frontmatter
from factory.genres import GenreError, load_genre, stage_allowed
from factory.project import ProjectError, load_project
from factory.safety import inside, is_safe_name

# Разделители файловых блоков. Не JSON: длинный текст с кавычками и переводами
# строк ломает JSON регулярно, а такую разметку переживает всё, кроме
# буквального совпадения самой строки-разделителя.
FILE_OPEN = "=== FILE:"
FILE_CLOSE = "=== END FILE ==="
_BLOCK = re.compile(
    r"===\s*FILE:\s*(?P<path>[^=\n]+?)\s*===\n(?P<body>.*?)\n?===\s*END FILE\s*===",
    re.DOTALL)


class StageError(ValueError):
    """Стадию не собрать или ответ не разложить."""


@dataclass(frozen=True)
class Stage:
    """Описание текстовой стадии как данных."""
    id: str
    label: str
    skill: str
    # Что читаем на вход. `{ep}` подставляется номером серии.
    inputs: tuple[str, ...] = ()
    # Куда разрешено писать. Пусто — стадия ничего не пишет (питч).
    outputs: tuple[str, ...] = ()
    # Стадия требует ответа человека прежде, чем что-то записать.
    interactive: bool = False
    # Соответствующая стадия конвейера: по ней жанр решает, существует ли она.
    pipeline_stage: str | None = None
    # Стадия существует только там, где жанр объявил fact_check: required.
    # Данные, а не проверка на месте: спрашивают об этом панель и CLI.
    requires_fact_check: bool = False


STAGES: dict[str, Stage] = {
    "pitch": Stage(
        id="pitch", label="Питч", skill="factory-pitch",
        inputs=("project.json", "bible/refs/", "research.md"),
        outputs=(), interactive=True, pipeline_stage="story"),
    "research": Stage(
        id="research", label="Исследование", skill="factory-research",
        inputs=("project.json",), outputs=("research.md",),
        pipeline_stage="research"),
    "story": Stage(
        id="story", label="Библия и арка", skill="factory-story",
        inputs=("project.json", "bible/idea.md", "research.md"),
        outputs=("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md",
                 "bible/craft-notes.md"),
        pipeline_stage="story"),
    "script": Stage(
        id="script", label="Сценарий", skill="factory-script",
        inputs=("project.json", "bible/idea.md", "bible/season-arc.md",
                "bible/craft-notes.md", "episodes/{ep}/script.md"),
        outputs=("episodes/{ep}/script.md",), pipeline_stage="script"),
    # Вход у проверки один — сам сценарий. Это и есть «пустой контекст» из
    # карточки жанра: проверяющий не видит ни идеи, ни арки, ни правил ремесла,
    # то есть не наследует уверенности того, кто сценарий писал.
    "factcheck": Stage(
        id="factcheck", label="Проверка фактов", skill="factory-factcheck",
        inputs=("episodes/{ep}/script.md",),
        outputs=("episodes/{ep}/script.md", "episodes/{ep}/fact-check.md"),
        pipeline_stage="script", requires_fact_check=True),
    "characters": Stage(
        id="characters", label="Персонажи", skill="factory-characters",
        inputs=("project.json", "bible/style-guide.md", "episodes/{ep}/script.md"),
        outputs=("bible/characters/",), pipeline_stage="characters"),
    "storyboard": Stage(
        id="storyboard", label="Раскадровка", skill="factory-storyboard",
        inputs=("project.json", "bible/style-guide.md", "bible/craft-notes.md",
                "episodes/{ep}/script.md"),
        outputs=("episodes/{ep}/shots.json",), pipeline_stage="storyboard"),
    # Имя `audio_plan`, а не `audio`: платная стадия озвучки называется
    # `audio`, и одно имя на две разные работы означало, что резолвер не может
    # назвать эту — он её и не называл никогда (ревью 2026-09-09). Скилл при
    # этом остаётся `factory-audio`: методика одна.
    "audio_plan": Stage(
        id="audio_plan", label="План звука", skill="factory-audio",
        inputs=("project.json", "bible/craft-notes.md",
                "episodes/{ep}/script.md", "episodes/{ep}/shots.json"),
        outputs=("episodes/{ep}/audio.json",), pipeline_stage="storyboard"),
}


@dataclass
class Prompt:
    """Готовый запрос к модели."""
    system: str
    user: str
    stage: Stage
    outputs: tuple[str, ...] = field(default_factory=tuple)


# --- сборка ---------------------------------------------------------------

def skill_body(repo_root: Path | str, skill: str) -> str:
    """Тело скилла без frontmatter: методика, написанная для человека и агента."""
    path = Path(repo_root) / ".claude" / "skills" / skill / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StageError(f"скилл {skill} не читается: {e}") from None
    try:
        _meta, body = split_frontmatter(text, path)
    except ArtifactError:
        return text
    return body


def _resolve(paths: tuple[str, ...], episode: str | None) -> list[str]:
    out = []
    for p in paths:
        if "{ep}" in p:
            if not episode:
                continue
            p = p.replace("{ep}", episode)
        out.append(p)
    return out


def build_prompt(stage_id: str, project_dir: Path | str, repo_root: Path | str,
                 *, request: str = "", episode: str | None = None,
                 extra: str = "") -> Prompt:
    """Собрать запрос к модели для текстовой стадии.

    `extra` — раздел задания, который собрал КОД, а не человек: список
    утверждений и выдержки поиска у проверки фактов. От `request` отличается
    происхождением, и путать их нельзя: `request` печатается как «что просит
    человек», и выдержки поиска под этой шапкой были бы враньём об источнике.
    """
    stage = STAGES.get(stage_id)
    if stage is None:
        raise StageError(
            f"неизвестная стадия {stage_id!r}; известны: {sorted(STAGES)}")

    project_dir = Path(project_dir)
    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        raise StageError(f"непригодный project.json: {e}") from None

    try:
        genre = load_genre(Path(repo_root) / "knowledge", project.genre)
    except GenreError as e:
        raise StageError(str(e)) from None

    if stage.pipeline_stage and not stage_allowed(genre, stage.pipeline_stage):
        raise StageError(
            f"стадия {stage_id!r} не существует у жанра {genre['id']!r}: "
            f"его стадии — {genre['stages']}")

    genre_body = (Path(repo_root) / "knowledge" / "genres" /
                  f"{genre['id']}.md").read_text(encoding="utf-8")

    system = "\n\n".join([
        skill_body(repo_root, stage.skill),
        "## Жанр проекта\n\n" + genre_body,
        _format_rules(),
    ])

    outputs = tuple(_resolve(stage.outputs, episode))
    user = _build_task(project_dir, project, stage, outputs, request, episode)
    if extra.strip():
        user = user + "\n\n" + extra.strip()
    return Prompt(system=system, user=user, stage=stage, outputs=outputs)


def _format_rules() -> str:
    """Как модель обязана отдать результат."""
    return (
        "## Формат ответа\n\n"
        "Файлы отдавай блоками, каждый целиком:\n\n"
        f"```\n{FILE_OPEN} путь/от/корня/проекта.md ===\n"
        f"<содержимое файла>\n{FILE_CLOSE}\n```\n\n"
        "Путь — только из списка ожидаемых файлов задания. Ничего, кроме этих "
        "файлов, не пиши: остальное скажи обычным текстом до или после блоков.")


def _build_task(project_dir: Path, project, stage: Stage,
                outputs: tuple[str, ...], request: str,
                episode: str | None) -> str:
    parts = [f"# Задание: {stage.label}", ""]
    parts.append(f"Проект: {project.name}. Тема: {project.theme}.")
    parts.append(f"Жанр: {project.genre}. Формат: {project.format}. "
                 f"Язык контента: {project.language}.")
    if episode:
        parts.append(f"Серия: {episode}.")
    parts.append("")

    parts.append("## Входные материалы")
    for rel in _resolve(stage.inputs, episode):
        path = project_dir / rel
        if rel.endswith("/"):
            listing = sorted(p.name for p in path.glob("*")) if path.is_dir() else []
            parts.append(f"\n### {rel}\n" + (", ".join(listing) or "пусто"))
            continue
        if not path.is_file():
            parts.append(f"\n### {rel}\nфайла нет")
            continue
        try:
            parts.append(f"\n### {rel}\n```\n"
                         + path.read_text(encoding="utf-8").strip() + "\n```")
        except OSError as e:
            parts.append(f"\n### {rel}\nне читается: {e}")

    parts.append("")
    if outputs:
        parts.append("## Ожидаемые файлы")
        parts += [f"- {rel}" for rel in outputs]
    else:
        parts.append("## Файлы\n\nНичего не записывай: это разговор, а не артефакт.")

    if request.strip():
        parts.append("\n## Что просит человек\n\n" + request.strip())
    return "\n".join(parts)


# --- разбор ---------------------------------------------------------------

def parse_files(answer: str) -> dict[str, str]:
    """Вытащить файлы из ответа модели."""
    files = {m.group("path").strip(): m.group("body")
             for m in _BLOCK.finditer(answer or "")}
    if not files:
        raise StageError(
            "в ответе модели нет ни одного файлового блока "
            f"({FILE_OPEN} … {FILE_CLOSE})")
    return files


def write_files(stage_id: str, project_dir: Path | str, files: dict[str, str],
                *, episode: str | None = None) -> list[str]:
    """Записать файлы стадии. Путь из ответа модели проверяется дважды.

    Данные, которые пишет модель, не становятся путями без проверки: сначала
    путь обязан входить в объявленные выходы стадии, потом — не выходить за
    корень проекта. Это то же правило, что закрыло `refs` в shots.json и `id` в
    audio.json (ревью безопасности 2026-09-05).
    """
    stage = STAGES.get(stage_id)
    if stage is None:
        raise StageError(f"неизвестная стадия {stage_id!r}")
    if not stage.outputs:
        raise StageError(
            f"стадия {stage_id!r} ничего не записывает: это разговор, "
            "а не артефакт")

    project_dir = Path(project_dir)
    allowed = _resolve(stage.outputs, episode)
    written: list[str] = []

    for rel, body in files.items():
        rel = rel.strip().replace("\\", "/")
        if not _allowed(rel, allowed):
            raise StageError(
                f"стадия {stage_id!r} не пишет в {rel!r}; "
                f"разрешено: {allowed}")

        parts = [p for p in rel.split("/") if p]
        if not parts or not all(is_safe_name(p) for p in parts):
            raise StageError(f"негодный путь из ответа модели: {rel!r}")

        target = project_dir / rel
        if not inside(project_dir, target):
            raise StageError(f"путь выходит за пределы проекта: {rel!r}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_with_frontmatter(target, rel, body), encoding="utf-8")
        written.append(rel)
    return written


def _allowed(rel: str, allowed: list[str]) -> bool:
    for pattern in allowed:
        if pattern.endswith("/"):
            if rel.startswith(pattern):
                return True
        elif rel == pattern:
            return True
    return False


def _with_frontmatter(target: Path, rel: str, body: str) -> str:
    """Артефакт сохраняется черновиком, а чужой frontmatter — сохраняется.

    `status: approved` ставит ТОЛЬКО `factory.py approve` — правило спеки
    пре-продакшна. Стадия, которая сама себя одобряет, обесценивает чекпоинт.
    JSON-файлы (shots.json, audio.json) frontmatter не имеют и пишутся как есть.

    Frontmatter УЖЕ СУЩЕСТВУЮЩЕГО файла переносится в новую версию, когда модель
    вернула одно тело. Причина конкретная: проверка фактов правит текст сценария
    точечно и frontmatter не пишет вовсе, а в нём живёт поле `characters` —
    состав серии. Затереть его значит отправить персонажа в платную генерацию без
    карточки и без референса, и ни один гейт этого не поймает: он просто не
    узнает, что такой персонаж существует. Правка тела при этом честно ломает
    `content_sha`, и уже одобренный артефакт становится `stale_self` — то есть
    просит перечитать себя заново, как и должен.
    """
    text = body.strip("\n") + "\n"
    if rel.endswith(".json") or text.lstrip().startswith("---"):
        return text
    try:
        meta, _old_body = split_frontmatter(target.read_text(encoding="utf-8"),
                                            target)
    except (ArtifactError, OSError):
        meta = {}
    if not meta:
        return f"---\nstatus: draft\n---\n{text}"
    meta.setdefault("status", "draft")
    front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    return f"---\n{front}\n---\n{text}"
