"""Загрузка и валидация project.json (бриф проекта, спека §4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VALID_QUALITY = {"high": 5, "budget": 10}  # режим -> секунд на отрезок (спека §4)
VALID_STRICTNESS = {"low", "medium", "high"}

# Обязательные поля по типам контента (ТЗ п.1.1–1.5)
REQUIRED_BY_TYPE = {
    "film": ["duration_sec", "theme"],
    "series": ["theme", "episodes", "episode_duration_sec"],
    "animated_film": ["duration_sec", "theme", "audience"],
    "animated_series": ["theme", "audience", "episodes", "episode_duration_sec"],
    "shorts": ["duration_sec", "theme"],
}


class ProjectError(ValueError):
    pass


@dataclass
class Project:
    name: str
    type: str
    theme: str
    language: str
    models: dict[str, str]
    quality_mode: str
    review_strictness: str
    raw: dict

    @property
    def segment_seconds(self) -> int:
        return VALID_QUALITY[self.quality_mode]


def load_project(path: Path) -> Project:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    ptype = data.get("type")
    if ptype not in REQUIRED_BY_TYPE:
        raise ProjectError(f"unknown project type: {ptype!r}")

    missing = [f for f in REQUIRED_BY_TYPE[ptype] if f not in data]
    if missing:
        raise ProjectError(f"missing required fields for {ptype}: {missing}")

    if "name" not in data:
        raise ProjectError("missing required field: 'name'")

    if not isinstance(data.get("models"), dict):
        raise ProjectError("models is required")

    for m in ("image", "video"):
        if m not in data["models"]:
            raise ProjectError(f"models.{m} is required")

    quality = data.get("quality_mode", "high")
    if quality not in VALID_QUALITY:
        raise ProjectError(f"unknown quality_mode: {quality!r}")

    strictness = data.get("review_strictness", "medium")
    if strictness not in VALID_STRICTNESS:
        raise ProjectError(f"unknown review_strictness: {strictness!r}")

    return Project(
        name=data["name"], type=ptype, theme=data["theme"],
        language=data.get("language", "en"), models=data["models"],
        quality_mode=quality, review_strictness=strictness, raw=data,
    )
