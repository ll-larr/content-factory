"""Каталог текстовых моделей: выбор человека и цены из первоисточника."""
import json
import time

import pytest

from factory.text import catalog

RAW = {"data": [
    {"id": "anthropic/claude-opus-5",
     "pricing": {"prompt": "0.000005", "completion": "0.000025"}},
    {"id": "anthropic/claude-opus-5:batch",
     "pricing": {"prompt": "0.0000025", "completion": "0.0000125"}},
    {"id": "~anthropic/claude-opus-latest", "pricing": {}},
    {"id": "deepseek/deepseek-v4-pro",
     "pricing": {"prompt": "0.00000096", "completion": "0.00000191"}},
    {"id": "openai/gpt-6-astra",
     "pricing": {"prompt": "0.00001", "completion": "0.00005"}},
    {"id": "mistralai/mistral-small", "pricing": {"prompt": "0.0000002"}},
]}


@pytest.fixture
def fetched(monkeypatch):
    calls = {"n": 0}

    def fake_fetch():
        calls["n"] += 1
        return RAW

    monkeypatch.setattr(catalog, "_fetch", fake_fetch)
    return calls


def test_only_allowed_families_are_offered(fetched, tmp_path):
    models = catalog.text_models(cache_dir=tmp_path)
    ids = {m["id"] for m in models}

    assert "anthropic/claude-opus-5" in ids
    assert "deepseek/deepseek-v4-pro" in ids
    assert "openai/gpt-6-astra" in ids
    # Не из списка человека — не предлагаем: выбор из четырёхсот моделей это не выбор.
    assert "mistralai/mistral-small" not in ids


def test_batch_and_alias_ids_are_hidden(fetched, tmp_path):
    ids = {m["id"] for m in catalog.text_models(cache_dir=tmp_path)}
    assert not any(i.endswith(":batch") for i in ids)
    assert not any(i.startswith("~") for i in ids)


def test_prices_come_from_catalog_in_dollars_per_million(fetched, tmp_path):
    models = {m["id"]: m for m in catalog.text_models(cache_dir=tmp_path)}
    opus = models["anthropic/claude-opus-5"]
    assert opus["input_per_million"] == pytest.approx(5.0)
    assert opus["output_per_million"] == pytest.approx(25.0)


def test_models_carry_family_and_label(fetched, tmp_path):
    models = {m["id"]: m for m in catalog.text_models(cache_dir=tmp_path)}
    assert models["deepseek/deepseek-v4-pro"]["family"] == "deepseek"
    assert models["anthropic/claude-opus-5"]["label"]


def test_catalog_is_cached_between_calls(fetched, tmp_path):
    catalog.text_models(cache_dir=tmp_path)
    catalog.text_models(cache_dir=tmp_path)
    assert fetched["n"] == 1, "каталог не должен дёргать сеть на каждое открытие панели"


def test_stale_cache_is_refetched(fetched, tmp_path):
    catalog.text_models(cache_dir=tmp_path)
    cache = tmp_path / catalog.CACHE_NAME
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["fetched_at"] = time.time() - catalog.CACHE_TTL_SECONDS - 10
    cache.write_text(json.dumps(data), encoding="utf-8")

    catalog.text_models(cache_dir=tmp_path)
    assert fetched["n"] == 2


def test_network_failure_falls_back_to_cache(monkeypatch, tmp_path, fetched):
    catalog.text_models(cache_dir=tmp_path)

    def boom():
        raise catalog.CatalogError("сеть недоступна")

    monkeypatch.setattr(catalog, "_fetch", boom)
    cache = tmp_path / catalog.CACHE_NAME
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["fetched_at"] = 0
    cache.write_text(json.dumps(data), encoding="utf-8")

    models = catalog.text_models(cache_dir=tmp_path)
    assert models, "устаревший кэш лучше пустого списка: выбирать всё равно есть из чего"


def test_no_cache_and_no_network_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog, "_fetch",
                        lambda: (_ for _ in ()).throw(catalog.CatalogError("нет сети")))
    with pytest.raises(catalog.CatalogError):
        catalog.text_models(cache_dir=tmp_path)


# --- «только актуальные»: каталог держит всю историю линейки (2026-09-12) ---

HISTORY = {"data": [{"id": i, "pricing": {"prompt": "0.000001",
                                          "completion": "0.000002"}}
                    for i in [
    "deepseek/deepseek-chat", "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-chat-v3.1", "deepseek/deepseek-v3.2",
    "deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-pro-0813",
    "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash-vision-exp",
    "google/gemini-2.5-pro", "google/gemini-3.1-pro-preview",
    "google/gemini-3.8-flash", "google/gemini-3-pro-image",
    "openai/gpt-5", "openai/gpt-5-mini", "openai/gpt-5.1-codex",
    "openai/gpt-5.6-luna", "openai/gpt-5.6-luna-pro", "openai/gpt-5.6-sol",
    "openai/gpt-5.6-sol-pro", "openai/gpt-5.6-terra", "openai/gpt-5.6-terra-pro",
    "x-ai/grok-4.20", "x-ai/grok-4.6",
]]}


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setattr(catalog, "_fetch", lambda: HISTORY)


def _ids(tmp_path):
    return {m["id"] for m in catalog.text_models(cache_dir=tmp_path)}


def test_only_the_latest_of_each_line_is_offered(history, tmp_path):
    ids = _ids(tmp_path)

    assert "deepseek/deepseek-v4.1-flash" in ids      # линия flash: свежая
    assert "deepseek/deepseek-v4-pro" in ids          # линия pro живёт своей версией
    assert "deepseek/deepseek-chat-v3.1" not in ids   # мажор 3 при живом 4 — история
    assert "deepseek/deepseek-v3.2" not in ids


def test_dated_snapshots_and_other_modalities_are_hidden(history, tmp_path):
    ids = _ids(tmp_path)

    assert "deepseek/deepseek-v4-pro-0813" not in ids     # тот же выпуск, прибитый к дате
    assert "deepseek/deepseek-v4-flash-vision-exp" not in ids
    assert "google/gemini-3-pro-image" not in ids         # другая модальность
    assert "openai/gpt-5.1-codex" not in ids              # модель под код, а не под сценарий


def test_a_newer_flash_does_not_bury_an_older_pro(history, tmp_path):
    """У Gemini pro последний 3.1, а flash уже 3.8 — обе строки нужны."""
    ids = _ids(tmp_path)

    assert {"google/gemini-3.1-pro-preview", "google/gemini-3.8-flash"} <= ids
    assert "google/gemini-2.5-pro" not in ids


def test_version_is_read_as_a_decimal_not_as_semver(history, tmp_path):
    """`grok-4.20` — это «четыре-двадцать», то есть СТАРШЕ 4.6 быть не может."""
    ids = _ids(tmp_path)

    assert "x-ai/grok-4.6" in ids
    assert "x-ai/grok-4.20" not in ids


def test_family_list_stays_short_enough_to_choose_from(history, tmp_path):
    models = catalog.text_models(cache_dir=tmp_path)
    per_family: dict[str, int] = {}
    for m in models:
        per_family[m["family"]] = per_family.get(m["family"], 0) + 1

    assert max(per_family.values()) <= catalog._PER_FAMILY
    # Линейка, вышедшая сразу тремя именами, помещается целиком.
    assert per_family["gpt-5"] == 6
    assert "openai/gpt-5-mini" not in _ids(tmp_path)
