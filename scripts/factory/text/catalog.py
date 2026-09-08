"""Какие текстовые модели предлагать человеку и по какой цене.

Список берётся из каталога OpenRouter (`GET /api/v1/models`) — он публичный, без
ключа, и отдаёт цены. Выдумывать идентификаторы и цены нельзя: они меняются, а
ошибка здесь стоит денег человека.

Из четырёхсот с лишним моделей показываются семь семейств, названных человеком:
выбор из всего каталога — это не выбор.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_NAME = "openrouter-models.json"
CACHE_TTL_SECONDS = 24 * 3600

# Семейства, которые человек выбрал 2026-09-07. Ключ — подстрока идентификатора,
# значение — как показать в панели.
FAMILIES = {
    "deepseek/": "DeepSeek",
    "anthropic/claude-opus": "Claude Opus",
    "anthropic/claude-fable": "Claude Fable",
    "x-ai/grok": "Grok",
    "google/gemini": "Gemini",
    "openai/gpt-5": "GPT-5",
    "openai/gpt-6": "GPT-6",
}


class CatalogError(RuntimeError):
    """Каталог моделей не получить."""


def _fetch() -> dict:
    try:
        with urllib.request.urlopen(CATALOG_URL, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        raise CatalogError(f"каталог моделей недоступен: {e}") from None


def _family(model_id: str) -> tuple[str, str] | None:
    for prefix, label in FAMILIES.items():
        if model_id.startswith(prefix) or prefix in model_id:
            return prefix, label
    return None


def _per_million(pricing: dict, key: str) -> float | None:
    """Цена за миллион токенов. Каталог отдаёт цену за токен строкой."""
    raw = pricing.get(key)
    if raw in (None, ""):
        return None
    try:
        return float(raw) * 1_000_000
    except (TypeError, ValueError):
        return None


def _shape(raw: dict) -> list[dict]:
    models = []
    for item in raw.get("data", []):
        model_id = item.get("id", "")
        # `:batch` — отложенная очередь, `~` — плавающий алиас. Ни то, ни другое
        # не годится: панель обещает конкретную модель по конкретной цене.
        if not model_id or model_id.endswith(":batch") or model_id.startswith("~"):
            continue
        family = _family(model_id)
        if family is None:
            continue
        prefix, label = family
        pricing = item.get("pricing") or {}
        models.append({
            "id": model_id,
            "family": prefix.rstrip("/").split("/")[-1] or prefix.strip("/"),
            "label": f"{label} · {model_id.split('/')[-1]}",
            "input_per_million": _per_million(pricing, "prompt"),
            "output_per_million": _per_million(pricing, "completion"),
        })
    return sorted(models, key=lambda m: m["id"])


def text_models(cache_dir: Path | str = Path(".")) -> list[dict]:
    """Модели для выбора в панели. Сеть дёргается не чаще раза в сутки."""
    cache = Path(cache_dir) / CACHE_NAME
    cached = None
    if cache.is_file():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None

    fresh = (cached is not None
             and time.time() - float(cached.get("fetched_at", 0)) < CACHE_TTL_SECONDS)
    if fresh:
        return _shape(cached["raw"])

    try:
        raw = _fetch()
    except CatalogError:
        # Устаревший кэш лучше пустого списка: выбирать всё равно есть из чего,
        # а цены за сутки не меняются в разы.
        if cached is not None:
            return _shape(cached["raw"])
        raise

    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fetched_at": time.time(), "raw": raw}),
                         encoding="utf-8")
    except OSError:
        pass          # кэш — удобство, а не условие работы
    return _shape(raw)
