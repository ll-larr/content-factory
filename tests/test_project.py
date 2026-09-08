import json
from pathlib import Path

import pytest

from factory.project import load_project, ProjectError

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


def write(tmp_path, data):
    p = tmp_path / "project.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


BASE = {
    "name": "pilot", "type": "animated_series", "theme": "space cats",
    "audience": "6-9", "episodes": 1, "episode_duration_sec": 75,
    "models": {"image": "nano-banana-2", "video": "kling-2.0"},
}


def test_loads_valid_animated_series(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.type == "animated_series"
    assert p.segment_seconds == 5            # high quality — дефолт
    assert p.review_strictness == "medium"   # дефолт


def test_budget_mode_gives_10s_segments(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "quality_mode": "budget"}))
    assert p.segment_seconds == 10


def test_missing_required_field_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "audience"}
    with pytest.raises(ProjectError, match="audience"):
        load_project(write(tmp_path, data))


def test_unknown_type_raises(tmp_path):
    with pytest.raises(ProjectError, match="unknown project type"):
        load_project(write(tmp_path, {**BASE, "type": "opera"}))


def test_missing_video_model_raises(tmp_path):
    with pytest.raises(ProjectError, match="models.video"):
        load_project(write(tmp_path, {**BASE, "models": {"image": "nano-banana-2"}}))


def test_missing_name_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "name"}
    with pytest.raises(ProjectError, match="name"):
        load_project(write(tmp_path, data))


def test_missing_models_entirely_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "models"}
    with pytest.raises(ProjectError, match="models is required"):
        load_project(write(tmp_path, data))


def test_unknown_strictness_raises(tmp_path):
    with pytest.raises(ProjectError, match="unknown review_strictness"):
        load_project(write(tmp_path, {**BASE, "review_strictness": "paranoid"}))


def test_max_rejections_default(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.max_rejections == 2


def test_max_rejections_custom(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "max_rejections": 5}))
    assert p.max_rejections == 5


@pytest.mark.parametrize("bad", [-1, "2", 1.5, True])
def test_max_rejections_invalid_raises(tmp_path, bad):
    with pytest.raises(ProjectError, match="max_rejections"):
        load_project(write(tmp_path, {**BASE, "max_rejections": bad}))


def test_max_rejections_zero_is_valid(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "max_rejections": 0}))
    assert p.max_rejections == 0


# --- провайдер / тир / разрешение (мультипровайдерный рефактор) ---

FILM = {"name": "f", "type": "film", "theme": "noir", "duration_sec": 60,
        "models": {"image": "seedream_4_5", "video": "seedance_2_0"}}


def test_video_string_uses_type_default_provider(tmp_path):
    """Строковая модель: провайдер выводится из типа (animated → runware)."""
    p = load_project(write(tmp_path, BASE))
    assert p.video_model == "kling-2.0"
    assert p.video_provider == "runware"      # animated_series → runware
    assert p.video_tier is None


def test_film_type_defaults_to_wavespeed(tmp_path):
    p = load_project(write(tmp_path, FILM))
    assert p.video_provider == "wavespeed"


def test_video_dict_provider_and_tier(tmp_path):
    data = {**BASE, "models": {"image": "nb2",
            "video": {"model": "seedance_2_0", "provider": "wavespeed", "tier": "fast"}}}
    p = load_project(write(tmp_path, data))
    assert p.video_model == "seedance_2_0"
    assert p.video_provider == "wavespeed"
    assert p.video_tier == "fast"


def test_image_provider_defaults_to_type(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.image_model == "nano-banana-2"
    assert p.image_provider == "runware"


def test_image_dict_overrides_provider(tmp_path):
    data = {**BASE, "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                               "video": "kling-2.0"}}
    p = load_project(write(tmp_path, data))
    assert p.image_provider == "wavespeed"


def test_image_dict_tier(tmp_path):
    """Объектная форма models.image несёт tier (симметрично video)."""
    data = {**BASE, "models": {
        "image": {"model": "z_image", "provider": "wavespeed", "tier": "hd"},
        "video": "kling-2.0"}}
    p = load_project(write(tmp_path, data))
    assert p.image_tier == "hd"


def test_image_string_tier_is_none(tmp_path):
    """Строковая models.image → tier не задан (None)."""
    p = load_project(write(tmp_path, BASE))
    assert p.image_tier is None


def test_resolution_default_720(tmp_path):
    assert load_project(write(tmp_path, BASE)).resolution == "720p"


def test_resolution_explicit_1080(tmp_path):
    assert load_project(write(tmp_path, {**BASE, "resolution": "1080p"})).resolution == "1080p"


def test_resolution_from_models_video(tmp_path):
    data = {**BASE, "models": {"image": "nb2",
            "video": {"model": "kling3_0", "provider": "wavespeed", "resolution": "1080p"}}}
    assert load_project(write(tmp_path, data)).resolution == "1080p"


def test_resolution_invalid_raises(tmp_path):
    with pytest.raises(ProjectError, match="resolution"):
        load_project(write(tmp_path, {**BASE, "resolution": "480p"}))


def test_video_dict_missing_model_raises(tmp_path):
    data = {**BASE, "models": {"image": "nb2", "video": {"provider": "wavespeed"}}}
    with pytest.raises(ProjectError, match="model"):
        load_project(write(tmp_path, data))


# --- модели звука (дизайн 2026-09-04 §4) ---

def test_audio_roles_default_to_wavespeed(tmp_path):
    # Провайдер звука по умолчанию НЕ зависит от типа контента, в отличие от
    # картинки и видео: аудио-моделей на Runware нет вовсе (modelSearch
    # 2026-09-04), и «дефолт по типу» отправил бы мультсериал туда, где TTS нет.
    data = json.loads(json.dumps(BASE))
    data["models"]["audio"] = {"tts": "gemini_2_5_pro_tts"}
    p = load_project(write(tmp_path, data))
    assert p.audio_model("tts") == "gemini_2_5_pro_tts"
    assert p.audio_provider("tts") == "wavespeed"


def test_audio_role_object_form(tmp_path):
    data = json.loads(json.dumps(BASE))
    data["models"]["audio"] = {
        "sfx": {"model": "mirelo_sfx_16", "provider": "wavespeed", "tier": "std"}}
    p = load_project(write(tmp_path, data))
    assert p.audio_model("sfx") == "mirelo_sfx_16"
    assert p.audio_tier("sfx") == "std"


def test_unknown_audio_role_raises(tmp_path):
    data = json.loads(json.dumps(BASE))
    data["models"]["audio"] = {"tts": "gemini_2_5_pro_tts"}
    p = load_project(write(tmp_path, data))
    with pytest.raises(ProjectError, match="music"):
        p.audio_model("music")


def test_audio_block_is_optional(tmp_path):
    # Проект без звука остаётся валидным: половина конвейера работает и молча.
    p = load_project(write(tmp_path, BASE))
    with pytest.raises(ProjectError, match="models.audio"):
        p.audio_model("tts")


# --- явная длительность отрезка (нужна veo: сетка 4/6/8) ---

def test_segment_seconds_override(tmp_path):
    # quality_mode даёт только 5 и 10; veo принимает 4, 6, 8 — без явного
    # переопределения модель формально открыта, но недостижима гейтом.
    p = load_project(write(tmp_path, {**BASE, "segment_seconds": 8}))
    assert p.segment_seconds == 8


def test_segment_seconds_must_be_positive_int(tmp_path):
    with pytest.raises(ProjectError, match="segment_seconds"):
        load_project(write(tmp_path, {**BASE, "segment_seconds": 0}))
    with pytest.raises(ProjectError, match="segment_seconds"):
        load_project(write(tmp_path, {**BASE, "segment_seconds": 4.5}))


def test_quality_mode_still_default(tmp_path):
    assert load_project(write(tmp_path, BASE)).segment_seconds == 5


# --- жанр, формат, режим кадров -------------------------------------------

GENRE_BASE = {"name": "п", "type": "animated_series", "theme": "т", "audience": "9-12",
        "episodes": 1, "episode_duration_sec": 60,
        "models": {"image": {"model": "z_image_turbo"},
                   "video": {"model": "vidu_q2_turbo"}}}


def brief(tmp_path, **over):
    """Бриф с жанром: имя отличается от write() выше — та принимает готовый dict."""
    data = {**GENRE_BASE, **over}
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_old_type_still_yields_genre_and_format(tmp_path):
    """Старые проекты не ломаются: за них уже заплачено генерациями."""
    p = load_project(brief(tmp_path))
    assert p.genre == "animation"
    assert p.format == "wide_16x9"
    assert p.aspect == "16:9"


def test_old_shorts_type_maps_to_vertical_format(tmp_path):
    p = load_project(brief(tmp_path, type="shorts", duration_sec=30))
    assert p.format == "shorts_9x16"
    assert p.aspect == "9:16"


def test_explicit_genre_beats_type(tmp_path):
    p = load_project(brief(tmp_path, genre="educational"))
    assert p.genre == "educational"


def test_explicit_format_beats_type(tmp_path):
    p = load_project(brief(tmp_path, format="shorts_9x16"))
    assert p.format == "shorts_9x16"
    assert p.aspect == "9:16"


def test_unknown_genre_rejected_by_name(tmp_path):
    with pytest.raises(ProjectError) as e:
        load_project(brief(tmp_path, genre="детектив"))
    assert "детектив" in str(e.value)


def test_unknown_format_rejected(tmp_path):
    with pytest.raises(ProjectError):
        load_project(brief(tmp_path, format="квадрат"))


def test_visual_mode_defaults_to_video_for_animation(tmp_path):
    assert load_project(brief(tmp_path)).visual_mode == "video"


def test_visual_mode_defaults_to_stills_for_educational(tmp_path):
    """Познавательному видеоряд чаще не нужен — и это дефолт жанра, не экономия."""
    p = load_project(brief(tmp_path, genre="educational"))
    assert p.visual_mode == "stills"


def test_explicit_visual_mode_wins(tmp_path):
    p = load_project(brief(tmp_path, genre="educational", visual_mode="video"))
    assert p.visual_mode == "video"


def test_visual_mode_must_be_allowed_by_genre(tmp_path):
    """Кино слайдшоу не снимают: режим объявляет карточка жанра."""
    with pytest.raises(ProjectError) as e:
        load_project(brief(tmp_path, genre="animation", visual_mode="stills"))
    assert "stills" in str(e.value)


def test_language_defaults_and_is_read(tmp_path):
    assert load_project(brief(tmp_path)).language == "en"
    assert load_project(brief(tmp_path, language="ru")).language == "ru"


def test_genre_card_is_reachable_from_project(tmp_path):
    """Гейтам и панели нужна не строка, а карточка со стадиями и запретами."""
    p = load_project(brief(tmp_path, genre="educational"))
    card = p.genre_card(KNOWLEDGE)
    assert card["lipsync"] is False
    assert "characters" not in card["stages"]
