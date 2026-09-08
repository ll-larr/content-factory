"""Плейсхолдеры в промптах кадров и их разворачивание (спека 2026-08-02 §10).

Промпт уходит по HTTP внешней модели — у неё нет файловой системы, поэтому
канонические блоки обязаны попасть в текст дословно. Плейсхолдер даёт дословность
кодом, а не дисциплиной: перефразировать при копировании физически некому.
"""
from __future__ import annotations

import re
from pathlib import Path

from factory.artifact import ArtifactError, canonical_block, has_canonical
from factory.preprod import artifact_state, is_safe_name

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)(?:\s*:\s*([\w\-]+))?\s*\}\}")
# Публичное имя (не приватное) — тем же паттерном ищут "любые фигурные скобки"
# и здесь, и generate_batch.py (гейт промпта движения отрезка). Раньше паттерн
# был продублирован буквально в обоих модулях — единственный источник истины.
PLACEHOLDER_ANY = re.compile(r"\{\{[^}]*\}\}")


class PromptError(ValueError):
    pass


def _block(path: Path, name: str) -> str:
    """canonical_block с ошибкой в терминах этого модуля.

    Разбор блока живёт в factory.artifact (чтение тела артефакта — его предмет, и
    так разорван цикл импортов с factory.preprod). Контракт разворачивания при
    этом не меняется: наружу по-прежнему летит PromptError, как и до переезда.
    """
    try:
        return canonical_block(path, name)
    except ArtifactError as e:
        raise PromptError(str(e)) from None


def _character_card(project_dir: Path, name: str) -> Path:
    """Путь карточки. Имя приходит из плейсхолдера {{char:...}} в shots.json, то
    есть из данных — компонент пути обязан быть одним сегментом (ревью 2026-08-02).
    Регулярка плейсхолдера уже не пропускает '/', но полагаться на неё одну нельзя:
    её легко ослабить, а последствие — чтение и запись вне проекта."""
    if not is_safe_name(name):
        raise PromptError(f"недопустимое имя персонажа {name!r}")
    return Path(project_dir) / "bible" / "characters" / f"{name}.md"


def expand_prompt(prompt: str, project_dir: Path) -> str:
    """Подставить канонические блоки вместо плейсхолдеров. Неизвестный плейсхолдер —
    ошибка, а не молчаливый пропуск: иначе провайдер получит текст с '{{...}}'."""
    project_dir = Path(project_dir)

    def replace(m: re.Match) -> str:
        kind, arg = m.group(1), m.group(2)
        if kind == "style" and arg is None:
            return _block(project_dir / "bible" / "style-guide.md", "style")
        if kind == "char" and arg:
            card = _character_card(project_dir, arg)
            if not card.exists():
                raise PromptError(f"нет карточки персонажа {arg!r} ({card})")
            return _block(card, "appearance")
        raise PromptError(f"неизвестный плейсхолдер {m.group(0)!r}")

    expanded = _PLACEHOLDER.sub(replace, prompt)
    # Подстановка идёт одним проходом и вставленное не пересматривает. Если
    # фигурные скобки были ВНУТРИ канонического блока, они уцелели бы и уехали
    # провайдеру буквально — оплаченный кадр с '{{...}}' в тексте.
    leftovers = PLACEHOLDER_ANY.findall(expanded)
    if leftovers:
        raise PromptError(
            f"после разворачивания остались плейсхолдеры {leftovers!r} — "
            "вероятно, они внутри канонического блока")
    return expanded


def leftover_braces(prompt: str) -> list[str]:
    """Куски вида {{...}}, которые НЕ распознаны как плейсхолдер.

    Отдельная проверка нужна потому, что `_PLACEHOLDER` намеренно узкий: `{{char:}}`
    с пустым именем или `{{ Style }}` он просто не увидит, и без этой проверки такой
    текст молча уехал бы провайдеру буквально — оплаченный кадр с фигурными скобками
    вместо описания персонажа.
    """
    stripped = _PLACEHOLDER.sub("", prompt)
    return PLACEHOLDER_ANY.findall(stripped)


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
        # artifact_state, а не meta["status"]: карточка, правленная после
        # одобрения (stale_self) или с уехавшим основанием (stale_deps), формально
        # несёт status: approved и проходила бы ПЛАТНЫЙ гейт, хотя factory.py check
        # её отбивает (находка финального ревью).
        state = artifact_state(project_dir, card)
        if state != "approved":
            problems.append(f"персонаж {arg!r}: карточка не одобрена ({state})")
        if not has_canonical(card, "appearance"):
            problems.append(f"персонаж {arg!r}: нет блока canonical:appearance")
        if f"{arg}-ref" not in refs_joined:
            problems.append(f"персонаж {arg!r}: нет его референса в refs кадра")
    return problems
