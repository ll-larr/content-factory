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
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ModelError(f"{path}: frontmatter is not closed with '---'")
    try:
        card = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        raise ModelError(f"{path}: invalid YAML — {e}") from None
    if not isinstance(card, dict):
        raise ModelError(f"{path}: frontmatter is not a YAML mapping")
    for req in ("id", "type", "status"):
        if req not in card:
            raise ModelError(f"{path}: frontmatter missing {req!r}")
    return card


def find_card(knowledge_dir: Path, model_id: str) -> dict:
    """Битые карточки пропускаются (не должны ломать поиск остальных);
    если модель не найдена — пропущенные перечисляются в ошибке."""
    skipped: list[str] = []
    for p in sorted(Path(knowledge_dir).rglob("*.md")):
        if p.name.startswith("_"):
            continue
        try:
            card = load_card(p)
        except ModelError:
            skipped.append(str(p))
            continue
        if card["id"] == model_id:
            return card
    msg = f"no knowledge card for model {model_id!r}"
    if skipped:
        msg += f" (skipped malformed cards: {', '.join(skipped)})"
    raise ModelError(msg)


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
    max_clip = card.get("max_clip_seconds", 0)
    if max_clip < segment_seconds:
        problems.append(
            f"{card['id']}: max clip {max_clip}s "
            f"< required {segment_seconds}s")
    # Проверяем сетку допустимых длительностей: None/[] = сетка неизвестна, не проверяем
    allowed = card.get("allowed_durations")
    if allowed and segment_seconds not in allowed:
        problems.append(
            f"{card['id']}: duration {segment_seconds}s not in allowed grid {allowed}")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems
