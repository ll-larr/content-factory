"""Карточки жанров: чем один тип контента отличается от другого.

Жанр — это данные, а не строка в конфиге. До этого модуля различия жили в головах
и в тексте скиллов, и каждая новая стадия писалась дважды: отдельно для
повествования с персонажами, отдельно для всего остального.

Устройство то же, что у карточек моделей (`factory/models.py`): frontmatter —
машине, проза — человеку и промптам творческих стадий. Один файл на жанр, и это
единственное место, где записано, что у познавательного нет персонажей, а у
мультфильма есть.
"""
from __future__ import annotations

from pathlib import Path

from factory.artifact import ArtifactError, split_frontmatter

GENRES_DIRNAME = "genres"

# Стадии, которые вообще существуют в конвейере. Карточка может их не
# перечислять, но выдумать свою не может: опечатка иначе породила бы стадию, за
# которую никто не отвечает.
KNOWN_STAGES = ("research", "story", "script", "characters", "storyboard")

VISUAL_MODES = ("video", "stills")
FACT_CHECK = ("none", "required")
CAPTIONS = ("shorts_only", "always", "never")

# Поля, без которых карточка бессмысленна: по ним код принимает решения.
REQUIRED = ("id", "label", "stages", "has_characters", "narrator", "lipsync",
            "captions", "fact_check", "visual_modes", "default_visual_mode",
            "shot_language", "requires_research", "animated")


class GenreError(ValueError):
    """Жанр не прочитать: нет карточки или она непригодна."""


def _cards_dir(knowledge_dir: Path | str) -> Path:
    return Path(knowledge_dir) / GENRES_DIRNAME


def load_card(path: Path) -> dict:
    """Прочитать карточку жанра и проверить её пригодность."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        card, _body = split_frontmatter(text, path)
    except ArtifactError as e:
        raise GenreError(f"{path}: {e}") from None

    missing = [key for key in REQUIRED if key not in card]
    if missing:
        raise GenreError(f"{path}: в карточке жанра нет полей {missing}")

    unknown = [s for s in card["stages"] if s not in KNOWN_STAGES]
    if unknown:
        raise GenreError(
            f"{path}: неизвестные стадии {unknown}; известны {list(KNOWN_STAGES)}")

    bad_modes = [m for m in card["visual_modes"] if m not in VISUAL_MODES]
    if bad_modes:
        raise GenreError(f"{path}: неизвестные режимы {bad_modes}")
    if card["default_visual_mode"] not in card["visual_modes"]:
        raise GenreError(
            f"{path}: режим по умолчанию {card['default_visual_mode']!r} "
            f"не входит в объявленные {card['visual_modes']}")
    if card["fact_check"] not in FACT_CHECK:
        raise GenreError(f"{path}: fact_check должен быть из {list(FACT_CHECK)}")
    if card["captions"] not in CAPTIONS:
        raise GenreError(f"{path}: captions должен быть из {list(CAPTIONS)}")
    return card


def all_genres(knowledge_dir: Path | str = Path("knowledge")) -> list[dict]:
    """Все жанры, о которых знает конвейер. Битая карточка — ошибка, не пропуск.

    В отличие от карточек моделей, где битую пропускают ради поиска остальных,
    здесь список короткий и целиком показывается человеку в панели: тихо
    потерянный жанр он заметит только тем, что не сможет создать проект.
    """
    directory = _cards_dir(knowledge_dir)
    if not directory.is_dir():
        raise GenreError(f"нет каталога жанров {directory}")
    return [load_card(p) for p in sorted(directory.glob("*.md"))
            if not p.name.startswith("_")]


def load_genre(knowledge_dir: Path | str, genre_id: str) -> dict:
    """Карточка одного жанра по идентификатору."""
    directory = _cards_dir(knowledge_dir)
    path = directory / f"{genre_id}.md"
    if path.is_file():
        return load_card(path)

    known = []
    if directory.is_dir():
        known = sorted(p.stem for p in directory.glob("*.md")
                       if not p.name.startswith("_"))
    raise GenreError(
        f"неизвестный жанр {genre_id!r}; известны: {', '.join(known) or '—'}")


def stage_allowed(card: dict, stage: str) -> bool:
    """Есть ли стадия у этого жанра.

    Отдельная функция, а не проверка на месте: спрашивают об этом гейты, смета и
    панель, и ответ у всех троих обязан быть один.
    """
    if stage == "lipsync":
        return bool(card.get("lipsync"))
    if stage in KNOWN_STAGES:
        return stage in card["stages"]
    return True
