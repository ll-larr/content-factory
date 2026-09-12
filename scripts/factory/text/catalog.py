"""Какие текстовые модели предлагать человеку и по какой цене.

Список берётся из каталога OpenRouter (`GET /api/v1/models`) — он публичный, без
ключа, и отдаёт цены. Выдумывать идентификаторы и цены нельзя: они меняются, а
ошибка здесь стоит денег человека.

Из четырёхсот с лишним моделей показываются семь семейств, названных человеком:
выбор из всего каталога — это не выбор. Внутри семейства остаются только
АКТУАЛЬНЫЕ модели: каталог держит всю историю линейки (у DeepSeek — от
`deepseek-chat` до `v4.1-flash`, у Gemini — от 2.5 до 3.8), и восемь десятков
строк в одном выпадающем списке — это тот же «выбор из всего каталога», только
на восьмую его часть. Правила отбора — в `_latest`.
"""
from __future__ import annotations

import json
import re
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


# Чем модель НЕ годится для текстовой стадии. Проверяется по словам
# идентификатора: каталог не объявляет назначение отдельным полем.
#
# image/vision/audio — другая модальность: стадия пишет текст, и платить за
# картиночную голову незачем. codex — модель под код, а у нас сценарий.
# preview/exp/customtools/multi-agent — вариации того же выпуска, которые
# отличаются доступом, а не качеством письма; `preview` пропускается только
# тогда, когда у выпуска есть обычный близнец (см. `_latest`).
_SKIP_WORDS = {"image", "vision", "audio", "tts", "embed", "embedding",
               "search", "online", "codex", "distill", "customtools"}
_SKIP_PHRASES = ("multi-agent",)
# Датированный снимок (`-0324`, `-05-06`) — это тот же выпуск, прибитый к дате.
_DATED = re.compile(r"-(\d{4}|\d{2}-\d{2})$")
_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)$")
# Сколько строк одного семейства показывать. Шесть — чтобы линейка, вышедшая
# сразу тремя именами с pro-вариантами (gpt-5.6 luna/sol/terra), поместилась
# целиком, а предыдущая уже нет.
_PER_FAMILY = 6


def _version(slug: str) -> float:
    """Версия из имени: `gpt-5.6-luna` → 5.6, `grok-4.20` → 4.2.

    Читается как ДЕСЯТИЧНОЕ число, а не как кортеж semver: в именах моделей
    `4.20` означает «четыре-двадцать», то есть выпуск между 4.1 и 4.3, — а
    покомпонентное сравнение поставило бы её выше 4.6. Третий компонент (редкий
    `2.5.1`) отбрасывается: он ничего не решает в этом списке.
    """
    for token in slug.split("-"):
        m = _VERSION.match(token)
        if m:
            parts = m.group(1).split(".")
            return float(".".join(parts[:2]))
    return 0.0


def _line(slug: str) -> tuple[str, ...]:
    """Линия модели: имя без версии и без пометки `preview`.

    `gpt-5.4-mini` и `gpt-5-mini` — одна линия (mini), `gpt-5.6-luna-pro` —
    своя. Так «последняя версия» считается по СВОЕЙ линии: иначе новый flash
    похоронил бы pro, который просто вышел раньше.
    """
    return tuple(t for t in slug.split("-")
                 if not _VERSION.match(t) and t != "preview")


def _latest(models: list[dict]) -> list[dict]:
    """Оставить по семейству только актуальное.

    Три правила, по нарастанию грубости:
    1. в каждой линии — максимальная версия (и не `preview`, если у той же
       версии есть близнец без пометки);
    2. линии старее ТЕКУЩЕГО МАЖОРА семейства выбрасываются целиком: пока
       DeepSeek на v4, строки v3.x — история, а не выбор;
    3. на семейство не больше `_PER_FAMILY` строк, сначала свежие.

    Мажор, а не полная версия: у Gemini pro последний — 3.1, а flash уже 3.8, и
    «оставить только самую свежую версию семейства» выкинуло бы pro совсем.
    """
    best: dict[tuple, dict] = {}
    for m in models:
        slug = m["id"].split("/")[-1]
        key = (m["family"], _line(slug))
        version = _version(slug)
        current = best.get(key)
        if current is None or version > current["_v"]:
            best[key] = {**m, "_v": version}
        elif (version == current["_v"]
              and "preview" in current["id"] and "preview" not in m["id"]):
            best[key] = {**m, "_v": version}

    top_major: dict[str, int] = {}
    for m in best.values():
        top_major[m["family"]] = max(top_major.get(m["family"], 0),
                                     int(m["_v"]))

    by_family: dict[str, list[dict]] = {}
    for m in sorted(best.values(), key=lambda m: (-m["_v"], m["id"])):
        if int(m["_v"]) < top_major[m["family"]]:
            continue
        rows = by_family.setdefault(m["family"], [])
        if len(rows) < _PER_FAMILY:
            rows.append(m)

    return sorted(({k: v for k, v in m.items() if k != "_v"}
                   for rows in by_family.values() for m in rows),
                  key=lambda m: m["id"])


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
        slug = model_id.split("/")[-1]
        if (_DATED.search(slug)
                or set(slug.split("-")) & _SKIP_WORDS
                or any(ph in slug for ph in _SKIP_PHRASES)):
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
    return _latest(models)


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
