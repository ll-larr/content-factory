"""Загрузка и валидация project.json (бриф проекта, спека §4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VALID_QUALITY = {"high": 5, "budget": 10}  # режим -> секунд на отрезок (спека §4)
VALID_STRICTNESS = {"low", "medium", "high"}
VALID_RESOLUTIONS = {"720p", "1080p"}

# Дефолтный видео/фото-провайдер по типу контента (FINAL §4); переопределяется
# полем provider в models.image/models.video.
DEFAULT_PROVIDER_BY_TYPE = {
    "film": "wavespeed",
    "series": "wavespeed",
    "shorts": "wavespeed",
    "animated_film": "runware",
    "animated_series": "runware",
}

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
    models: dict
    quality_mode: str
    review_strictness: str
    max_rejections: int
    resolution: str
    raw: dict

    @property
    def segment_seconds(self) -> int:
        return VALID_QUALITY[self.quality_mode]

    def _entry(self, key: str) -> tuple[str, str, str | None]:
        """Разобрать models[key] (строка или объект) → (model, provider, tier).

        Строка → провайдер по умолчанию из типа контента, tier=None.
        Объект {model, provider?, tier?} → явные значения с фолбэком провайдера.
        """
        raw = self.models[key]
        default_provider = DEFAULT_PROVIDER_BY_TYPE.get(self.type, "wavespeed")
        if isinstance(raw, dict):
            return (raw["model"], raw.get("provider", default_provider), raw.get("tier"))
        return (raw, default_provider, None)

    @property
    def video_model(self) -> str:
        return self._entry("video")[0]

    @property
    def video_provider(self) -> str:
        return self._entry("video")[1]

    @property
    def video_tier(self) -> str | None:
        return self._entry("video")[2]

    @property
    def image_model(self) -> str:
        return self._entry("image")[0]

    @property
    def image_provider(self) -> str:
        return self._entry("image")[1]

    @property
    def image_tier(self) -> str | None:
        return self._entry("image")[2]


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
        # Объектная форма {model, provider?, tier?, resolution?} — обязателен model
        entry = data["models"][m]
        if isinstance(entry, dict) and "model" not in entry:
            raise ProjectError(f"models.{m} object is missing required 'model'")

    # Разрешение: top-level или models.video.resolution; default 720p
    resolution = data.get("resolution")
    video_entry = data["models"]["video"]
    if resolution is None and isinstance(video_entry, dict):
        resolution = video_entry.get("resolution")
    resolution = resolution or "720p"
    if resolution not in VALID_RESOLUTIONS:
        raise ProjectError(
            f"unknown resolution: {resolution!r} (allowed: {sorted(VALID_RESOLUTIONS)})")

    quality = data.get("quality_mode", "high")
    if quality not in VALID_QUALITY:
        raise ProjectError(f"unknown quality_mode: {quality!r}")

    strictness = data.get("review_strictness", "medium")
    if strictness not in VALID_STRICTNESS:
        raise ProjectError(f"unknown review_strictness: {strictness!r}")

    max_rejections = data.get("max_rejections", 2)
    if (isinstance(max_rejections, bool) or not isinstance(max_rejections, int)
            or max_rejections < 0):
        raise ProjectError(
            f"max_rejections must be a non-negative int, got {max_rejections!r}")

    return Project(
        name=data["name"], type=ptype, theme=data["theme"],
        language=data.get("language", "en"), models=data["models"],
        quality_mode=quality, review_strictness=strictness,
        max_rejections=max_rejections, resolution=resolution, raw=data,
    )
