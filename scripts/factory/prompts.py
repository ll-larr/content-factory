"""Плейсхолдеры в промптах кадров и их разворачивание (спека 2026-08-02 §10).

Промпт уходит по HTTP внешней модели — у неё нет файловой системы, поэтому
канонические блоки обязаны попасть в текст дословно. Плейсхолдер даёт дословность
кодом, а не дисциплиной: перефразировать при копировании физически некому.
"""
from __future__ import annotations

import re
from pathlib import Path

from factory.artifact import load_artifact

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)(?:\s*:\s*([\w\-]+))?\s*\}\}")


class PromptError(ValueError):
    pass


def _canonical_re(name: str) -> re.Pattern:
    return re.compile(rf"<!--\s*canonical:{name}\s*-->(.*?)<!--\s*/canonical:{name}\s*-->",
                      re.DOTALL)


def canonical_block(path: Path, name: str) -> str:
    """Текст между маркерами <!-- canonical:<name> --> и закрывающим."""
    path = Path(path)
    if not path.exists():
        raise PromptError(f"{path}: файл не найден")
    match = _canonical_re(name).search(load_artifact(path).body)
    if not match:
        raise PromptError(f"{path}: нет блока canonical:{name}")
    return match.group(1).strip()


def _character_card(project_dir: Path, name: str) -> Path:
    return Path(project_dir) / "bible" / "characters" / f"{name}.md"


def expand_prompt(prompt: str, project_dir: Path) -> str:
    """Подставить канонические блоки вместо плейсхолдеров. Неизвестный плейсхолдер —
    ошибка, а не молчаливый пропуск: иначе провайдер получит текст с '{{...}}'."""
    project_dir = Path(project_dir)

    def replace(m: re.Match) -> str:
        kind, arg = m.group(1), m.group(2)
        if kind == "style" and arg is None:
            return canonical_block(project_dir / "bible" / "style-guide.md", "style")
        if kind == "char" and arg:
            card = _character_card(project_dir, arg)
            if not card.exists():
                raise PromptError(f"нет карточки персонажа {arg!r} ({card})")
            return canonical_block(card, "appearance")
        raise PromptError(f"неизвестный плейсхолдер {m.group(0)!r}")

    return _PLACEHOLDER.sub(replace, prompt)


def leftover_braces(prompt: str) -> list[str]:
    """Куски вида {{...}}, которые НЕ распознаны как плейсхолдер.

    Отдельная проверка нужна потому, что `_PLACEHOLDER` намеренно узкий: `{{char:}}`
    с пустым именем или `{{ Style }}` он просто не увидит, и без этой проверки такой
    текст молча уехал бы провайдеру буквально — оплаченный кадр с фигурными скобками
    вместо описания персонажа.
    """
    stripped = _PLACEHOLDER.sub("", prompt)
    return re.findall(r"\{\{[^}]*\}\}", stripped)


def prompt_problems(prompt: str, project_dir: Path, refs: list[str]) -> list[str]:
    """Проверки гейта раскадровки. Пустой список = промпт годен."""
    project_dir = Path(project_dir)
    problems: list[str] = []
    found = _PLACEHOLDER.findall(prompt)

    if not any(kind == "style" and not arg for kind, arg in found):
        problems.append("в промпте нет {{style}}")

    for junk in leftover_braces(prompt):
        problems.append(f"нераспознанный плейсхолдер {junk!r}")

    refs_joined = " ".join(refs)
    for kind, arg in found:
        if kind == "style":
            # {{style}} аргумента не принимает; {{style:foo}} прошёл бы гейт и упал
            # уже в expand_prompt — то есть после того, как смета показана человеку.
            if arg:
                problems.append(f"плейсхолдер {{{{style}}}} не принимает аргумент: {arg!r}")
            continue
        if kind != "char" or not arg:
            problems.append(f"неизвестный плейсхолдер {{{{{kind}}}}}")
            continue
        card = _character_card(project_dir, arg)
        if not card.exists():
            problems.append(f"персонаж {arg!r}: нет карточки {card.name}")
            continue
        if load_artifact(card).meta.get("status") != "approved":
            problems.append(f"персонаж {arg!r}: не одобрен")
        if f"{arg}-ref" not in refs_joined:
            problems.append(f"персонаж {arg!r}: нет его референса в refs кадра")
    return problems
