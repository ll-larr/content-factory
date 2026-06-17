"""Реестр провайдеров генерации. Higgsfield вырезан (FINAL §1)."""
from __future__ import annotations

from pathlib import Path

from factory.providers.base import ProviderError, VideoProvider
from factory.providers.openrouter import OpenRouterProvider
from factory.providers.runware import RunwareProvider
from factory.providers.wavespeed import WaveSpeedProvider

_REGISTRY = {
    "wavespeed": WaveSpeedProvider,
    "runware": RunwareProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str,
                 knowledge_dir: Path | str = Path("knowledge")) -> VideoProvider:
    """Фабрика провайдеров по имени из project.json (FINAL §5.3)."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ProviderError(
            f"unknown provider {name!r} (known: {sorted(_REGISTRY)})")
    return cls(knowledge_dir=knowledge_dir)
