"""Реестр провайдеров. Higgsfield вырезан (FINAL §1).

Реестра два, потому что поверхностей две: генерация медиа за деньги по карточке
модели и поиск в вебе для проверки фактов. Складывать их в один словарь значило
бы дать `project.json` возможность выбрать поисковик как видеопровайдер.
"""
from __future__ import annotations

from pathlib import Path

from factory.providers.base import ProviderError, SearchProvider, VideoProvider
from factory.providers.openrouter import OpenRouterProvider
from factory.providers.runware import RunwareProvider
from factory.providers.tavily import TavilyProvider
from factory.providers.wavespeed import WaveSpeedProvider

_REGISTRY = {
    "wavespeed": WaveSpeedProvider,
    "runware": RunwareProvider,
    "openrouter": OpenRouterProvider,
}

_SEARCH_REGISTRY = {
    "tavily": TavilyProvider,
}


def get_provider(name: str,
                 knowledge_dir: Path | str = Path("knowledge")) -> VideoProvider:
    """Фабрика провайдеров по имени из project.json (FINAL §5.3)."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ProviderError(
            f"unknown provider {name!r} (known: {sorted(_REGISTRY)})")
    return cls(knowledge_dir=knowledge_dir)


def get_search_provider(name: str | None = None) -> SearchProvider:
    """Провайдер поиска по имени; без имени — первый доступный по ключу.

    Отказ, а не None: тому, кто зовёт поиск, нужно объяснить, почему проверка
    фактов не идёт, — и объяснение здесь единственное, чтобы панель, гейт и CLI
    говорили одно и то же.
    """
    if name is not None:
        cls = _SEARCH_REGISTRY.get(name)
        if cls is None:
            raise ProviderError(
                f"unknown search provider {name!r} "
                f"(known: {sorted(_SEARCH_REGISTRY)})")
        found = cls()
        if not found.available():
            raise ProviderError(found.unavailable_reason())
        return found

    reasons = []
    for cls in _SEARCH_REGISTRY.values():
        candidate = cls()
        if candidate.available():
            return candidate
        reasons.append(candidate.unavailable_reason())
    raise ProviderError("поиск недоступен: " + "; ".join(reasons))


def is_search_provider(name: str) -> bool:
    """Имя принадлежит поисковой поверхности, а не генерации медиа.

    Нужна панели: `get_provider` на поисковике падает «unknown provider», и
    показывать этот текст человеку вместо причины прочерка в балансах значит
    врать о причине.
    """
    return name.lower() in _SEARCH_REGISTRY


def search_provider_states() -> list[dict]:
    """Состояние поисковых провайдеров — для панели и гейта жанра."""
    rows = []
    for name, cls in _SEARCH_REGISTRY.items():
        provider = cls()
        ok = provider.available()
        rows.append({"name": name, "available": ok,
                     "reason": "" if ok else provider.unavailable_reason()})
    return rows
