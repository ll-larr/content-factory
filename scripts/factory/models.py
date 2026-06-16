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


def validate_video_model(card: dict, segment_seconds: int,
                         provider: str | None = None) -> list[str]:
    """Спека §6: валидация выбора модели ДО траты денег.

    Если задан ``provider`` И в карте есть блок ``providers`` — проверяем
    возможности (start/end, сетку длительностей) ПОД ВЫБРАННОГО провайдера.
    Без ``provider`` (или если в карте нет ``providers``) — legacy-поведение
    по top-level полям карточки.
    """
    problems: list[str] = []
    if card["type"] != "video":
        problems.append(f"{card['id']}: not a video model")
        return problems

    providers = card.get("providers")
    if provider is not None and providers is not None:
        pv = providers.get(provider)
        if pv is None:
            problems.append(
                f"{card['id']}: not available on provider {provider!r} "
                f"(declared: {sorted(providers)})")
            return problems
        supports = pv.get("supports_start_end")
        allowed = pv.get("allowed_durations", card.get("allowed_durations"))
        max_clip = pv.get("max_clip_seconds")  # None → сетка неизвестна, не проверяем
    else:
        supports = card.get("supports_start_end_frame")
        allowed = card.get("allowed_durations")
        max_clip = card.get("max_clip_seconds", 0)

    if not supports:
        problems.append(
            f"{card['id']}: no start/end frame support — "
            "segment chaining (спека §4) will break")
    if max_clip is not None and max_clip < segment_seconds:
        problems.append(
            f"{card['id']}: max clip {max_clip}s "
            f"< required {segment_seconds}s")
    # Проверяем сетку допустимых длительностей: None/[] = сетка неизвестна, не проверяем
    if allowed and segment_seconds not in allowed:
        problems.append(
            f"{card['id']}: duration {segment_seconds}s not in allowed grid {allowed}")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems


def estimate_media_cost(card: dict, provider: str, resolution: str,
                        duration_sec: float, tier: str | None = None) -> float:
    """Смета в долларах под провайдера/разрешение/тип цены (ТЗ §6, FINAL §3).

    Источник цен — frontmatter карточки (блок ``providers``):
    - image / ``usd_per_image`` → плоская цена за изображение (разрешение/длительность
      не влияют);
    - video ``pricing: flat`` → ``usd_per_sec × duration_sec`` (от разрешения не зависит);
    - video ``pricing: scaled`` → ``usd_per_sec(720p) × duration_sec × res_mult[resolution]``
      (×1.4 WaveSpeed, ×2.25 OpenRouter/Runware).

    Тир (``fast``/``std``/``pro``) выбирает запись из ``providers[p].tiers``;
    по умолчанию — ``default_tier``.
    """
    providers = card.get("providers") or {}
    pv = providers.get(provider)
    if pv is None:
        raise ModelError(
            f"{card.get('id')}: no pricing for provider {provider!r} "
            f"(declared: {sorted(providers)})")

    entry = pv
    if "tiers" in pv:
        chosen = tier or pv.get("default_tier")
        if chosen not in pv["tiers"]:
            raise ModelError(
                f"{card.get('id')}: unknown tier {chosen!r} for provider {provider!r} "
                f"(declared: {sorted(pv['tiers'])})")
        entry = pv["tiers"][chosen]

    usd_per_image = entry.get("usd_per_image", pv.get("usd_per_image"))
    if usd_per_image is not None or card.get("type") == "image":
        if usd_per_image is None:
            raise ModelError(f"{card.get('id')}: no usd_per_image for provider {provider!r}")
        return float(usd_per_image)

    usd_per_sec = entry.get("usd_per_sec", pv.get("usd_per_sec"))
    if usd_per_sec is None:
        raise ModelError(f"{card.get('id')}: no usd_per_sec for provider {provider!r}")
    cost = float(usd_per_sec) * float(duration_sec)

    if pv.get("pricing") == "scaled":
        res_mult = pv.get("res_mult", {})
        if resolution not in res_mult:
            raise ModelError(
                f"{card.get('id')}: no res_mult for resolution {resolution!r} "
                f"on provider {provider!r}")
        cost *= float(res_mult[resolution])
    return cost


def validate_audio_model(card: dict) -> list[str]:
    """Валидация аудио-модели ДО траты кредитов (спека фазы 2 §5)."""
    problems: list[str] = []
    if card["type"] != "audio":
        problems.append(f"{card['id']}: not an audio model")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems
