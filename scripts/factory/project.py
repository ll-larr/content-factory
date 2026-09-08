"""Загрузка и валидация project.json (бриф проекта, спека §4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VALID_QUALITY = {"high": 5, "budget": 10}  # режим -> секунд на отрезок (спека §4)
VALID_STRICTNESS = {"low", "medium", "high"}
VALID_RESOLUTIONS = {"720p", "1080p"}

# Языки, на которых конвейер умеет делать контент. Список открытый: добавить
# язык — значит дописать сюда строку и убедиться, что у выбранной модели речи
# есть для него `language_map` (иначе поле language не уедет провайдеру вовсе).
LANGUAGES = {"ru": "Русский", "en": "English"}

# Дефолтный видео/фото-провайдер по типу контента (FINAL §4); переопределяется
# полем provider в models.image/models.video.
DEFAULT_PROVIDER_BY_TYPE = {
    "film": "wavespeed",
    "series": "wavespeed",
    "shorts": "wavespeed",
    "animated_film": "runware",
    "animated_series": "runware",
}

# Разложение старого поля `type` на жанр и формат. Раньше они были смешаны в
# одном значении, и «shorts» смешивал формат с жанром: познавательный шортс
# выразить было нечем. Старые проекты не ломаем — за их генерации заплачено.
TYPE_TO_GENRE_FORMAT = {
    "film": ("live_action", "wide_16x9"),
    "series": ("live_action", "wide_16x9"),
    "animated_film": ("animation", "wide_16x9"),
    "animated_series": ("animation", "wide_16x9"),
    "shorts": ("live_action", "shorts_9x16"),
}

# Форматы и соотношение сторон, которое каждый диктует генерации.
#
# Форматов ДВА, а не три (решение 2026-09-08). «Полный метр» и «сериал»
# различались только структурой брифа — одна длительность против количества
# серий, — а картинку давали одну и ту же, 16:9. Выбор между ними был выбором
# без последствий: метр это сериал из одной серии, и человек теперь пишет
# «серий: 1» вместо того, чтобы угадывать, какой из двух пунктов его.
FORMAT_ASPECT = {
    "wide_16x9": "16:9",
    "shorts_9x16": "9:16",
}

# Старые имена форматов. Брифы, созданные до слияния, читаются как были: за их
# генерации заплачено. Единственное место, где живёт это соответствие.
FORMAT_ALIASES = {
    "film_16x9": "wide_16x9",
    "series_16x9": "wide_16x9",
}

# Человеческие имена форматов — для мастера создания проекта в панели.
FORMAT_LABELS = {
    "wide_16x9": "Горизонтальное (16:9)",
    "shorts_9x16": "Вертикальное, шортс (9:16)",
}


def normalize_format(fmt: str) -> str:
    """Формат из брифа в текущем виде: старое имя разворачивается в новое."""
    return FORMAT_ALIASES.get(fmt, fmt)


def type_for(genre_card: dict, fmt: str) -> str:
    """Легаси-поле `type` из настоящей модели данных — жанра и формата.

    Единственное место, где `type` ВЫВОДИТСЯ. Само поле осталось только ради
    старых проектов (за их генерации заплачено) и двух карт, которые на нём
    висят: `REQUIRED_BY_TYPE` и `DEFAULT_PROVIDER_BY_TYPE`. Новый проект,
    созданный в панели, знает жанр и формат — и `type` для него вычисляется
    здесь, а не набирается человеком: набранный руками он однажды разойдётся с
    жанром, и никто не заметит.

    Рисованное отличается от снятого полем `animated` карточки жанра — тем же,
    что легаси-`type` и пытался закодировать словом `animated_*`.
    """
    fmt = normalize_format(fmt)
    if fmt not in FORMAT_ASPECT:
        raise ProjectError(
            f"unknown format: {fmt!r} (known: {sorted(FORMAT_ASPECT)})")
    if fmt == "shorts_9x16":
        # Отдельного `animated_shorts` в легаси-типах не было и не будет:
        # заводить новый `type` ради вертикального мультфильма значит
        # продлевать жизнь полю, которое мы и так держим только из-за старых
        # проектов. Жанр при этом никуда не девается — он в `genre`.
        return "shorts"
    # `film`/`animated_film` больше не ВЫВОДЯТСЯ: горизонтальный проект — всегда
    # сериал, у которого может быть одна серия. Читаться старые брифы с этими
    # типами продолжают (REQUIRED_BY_TYPE их знает).
    return "animated_series" if bool(genre_card.get("animated")) else "series"

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
    genre: str
    format: str
    visual_mode: str
    theme: str
    language: str
    models: dict
    quality_mode: str
    review_strictness: str
    max_rejections: int
    resolution: str
    raw: dict

    @property
    def aspect(self) -> str:
        """Соотношение сторон уходит в генерацию и в монтаж.

        Раньше считалось на месте как `"9:16" if project.type == "shorts"` в двух
        разных файлах; теперь его диктует формат, и жанр на него не влияет —
        познавательное бывает и горизонтальным, и вертикальным.
        """
        return FORMAT_ASPECT[self.format]

    def genre_card(self, knowledge_dir="knowledge") -> dict:
        """Карточка жанра: стадии, запреты, язык раскадровки.

        Гейтам, смете и панели нужна не строка жанра, а его правила, и правила
        эти живут в одном месте — `knowledge/genres/<id>.md`.
        """
        from factory.genres import load_genre
        return load_genre(knowledge_dir, self.genre)

    @property
    def segment_seconds(self) -> int:
        """Длительность отрезка: явная из брифа, иначе из режима качества.

        `quality_mode` даёт только 5 и 10 секунд, а сетки моделей этим не
        исчерпываются: veo 3.1 принимает 4, 6 и 8, и без явного переопределения
        модель формально открыта, но недостижима — гейт отбивает её сообщением
        про сетку длительностей ДО трат.
        """
        explicit = self.raw.get("segment_seconds")
        if explicit is not None:
            return int(explicit)
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

    # ---- звук (дизайн 2026-09-04 §4) ----
    # Провайдер звука по умолчанию НЕ зависит от типа контента, в отличие от
    # картинки и видео: аудио-моделей на Runware нет вовсе (modelSearch
    # 2026-09-04 по tts/sfx/music/foley — пусто), и «дефолт по типу» отправил бы
    # мультсериал туда, где TTS не существует.
    AUDIO_DEFAULT_PROVIDER = "wavespeed"

    def _audio_entry(self, role: str) -> tuple[str, str, str | None]:
        block = self.models.get("audio")
        if not isinstance(block, dict):
            raise ProjectError(
                "models.audio не объявлен — стадии звука недоступны; "
                "проект без звука валиден, эпизод собирается молча")
        if role not in block:
            raise ProjectError(
                f"models.audio.{role} не объявлен (есть: {sorted(block)})")
        raw = block[role]
        if isinstance(raw, dict):
            if "model" not in raw:
                raise ProjectError(f"models.audio.{role}: нет обязательного 'model'")
            return (raw["model"], raw.get("provider", self.AUDIO_DEFAULT_PROVIDER),
                    raw.get("tier"))
        return (raw, self.AUDIO_DEFAULT_PROVIDER, None)

    def audio_model(self, role: str) -> str:
        return self._audio_entry(role)[0]

    def audio_provider(self, role: str) -> str:
        return self._audio_entry(role)[1]

    def audio_tier(self, role: str) -> str | None:
        return self._audio_entry(role)[2]


def _genre_and_format(data: dict, ptype: str) -> tuple[str, str]:
    """Жанр и формат: явные поля сильнее выведенных из старого `type`."""
    from factory.genres import GenreError, all_genres

    default_genre, default_format = TYPE_TO_GENRE_FORMAT[ptype]
    genre = data.get("genre", default_genre)
    fmt = normalize_format(data.get("format", default_format))

    try:
        known = {card["id"] for card in all_genres(data.get("_knowledge", "knowledge"))}
    except GenreError:
        # Каталог жанров недоступен (например, запуск не из корня репозитория).
        # Это не повод не открыть проект: жанр проверят гейты, когда до них
        # дойдёт, и сообщение там будет точнее.
        known = None

    if known is not None and genre not in known:
        raise ProjectError(
            f"unknown genre: {genre!r} (known: {sorted(known)})")
    if fmt not in FORMAT_ASPECT:
        raise ProjectError(
            f"unknown format: {fmt!r} (known: {sorted(FORMAT_ASPECT)})")
    return genre, fmt


def _visual_mode(data: dict, genre: str) -> str:
    """Видеоряд или кадры под озвучку.

    Режим объявляет карточка жанра: кино слайдшоу не снимают, а познавательному
    видеоряд чаще не нужен вовсе — и это его норма, а не экономия.
    """
    from factory.genres import GenreError, load_genre

    try:
        card = load_genre(data.get("_knowledge", "knowledge"), genre)
    except GenreError:
        return data.get("visual_mode", "video")

    mode = data.get("visual_mode", card["default_visual_mode"])
    if mode not in card["visual_modes"]:
        raise ProjectError(
            f"visual_mode {mode!r} не разрешён жанром {genre!r} "
            f"(разрешены: {card['visual_modes']})")
    return mode


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

    seconds = data.get("segment_seconds")
    if seconds is not None:
        # Дробная или нулевая длительность до сети не дойдёт ни у одной модели,
        # а разбираться в отказе провайдера дороже, чем отказать по брифу.
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise ProjectError(
                f"segment_seconds must be a positive integer, got {seconds!r}")

    genre, fmt = _genre_and_format(data, ptype)
    visual_mode = _visual_mode(data, genre)

    strictness = data.get("review_strictness", "medium")
    if strictness not in VALID_STRICTNESS:
        raise ProjectError(f"unknown review_strictness: {strictness!r}")

    max_rejections = data.get("max_rejections", 2)
    if (isinstance(max_rejections, bool) or not isinstance(max_rejections, int)
            or max_rejections < 0):
        raise ProjectError(
            f"max_rejections must be a non-negative int, got {max_rejections!r}")

    return Project(
        name=data["name"], type=ptype, genre=genre, format=fmt,
        visual_mode=visual_mode, theme=data["theme"],
        language=data.get("language", "en"), models=data["models"],
        quality_mode=quality, review_strictness=strictness,
        max_rejections=max_rejections, resolution=resolution, raw=data,
    )
