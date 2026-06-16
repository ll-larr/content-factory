import json
import pytest
from factory.project import load_project, ProjectError


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
