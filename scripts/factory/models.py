"""Карточки моделей: YAML-frontmatter с матрицей возможностей (спека §6)."""
from __future__ import annotations

from pathlib import Path

import yaml


class ModelError(ValueError):
    pass


def load_card(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ModelError(f"{path}: card has no YAML frontmatter")
    _, fm, _body = text.split("---", 2)
    card = yaml.safe_load(fm)
    for req in ("id", "type", "status"):
        if req not in card:
            raise ModelError(f"{path}: frontmatter missing {req!r}")
    return card


def find_card(knowledge_dir: Path, model_id: str) -> dict:
    for p in sorted(Path(knowledge_dir).rglob("*.md")):
        if p.name.startswith("_"):
            continue
        card = load_card(p)
        if card["id"] == model_id:
            return card
    raise ModelError(f"no knowledge card for model {model_id!r}")


def validate_video_model(card: dict, segment_seconds: int) -> list[str]:
    """Спека §6: валидация выбора модели ДО траты кредитов."""
    problems: list[str] = []
    if card["type"] != "video":
        problems.append(f"{card['id']}: not a video model")
        return problems
    if not card.get("supports_start_end_frame"):
        problems.append(
            f"{card['id']}: no start/end frame support — "
            "segment chaining (спека §4) will break")
    if card.get("max_clip_seconds", 0) < segment_seconds:
        problems.append(
            f"{card['id']}: max clip {card.get('max_clip_seconds', 0)}s "
            f"< required {segment_seconds}s")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems
