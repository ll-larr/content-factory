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
