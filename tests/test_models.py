import pytest
from factory.models import (find_card, load_card, validate_video_model,
                            estimate_media_cost, ModelError)

CARD = """---
id: kling-2.0
type: video
family: kling
status: verified
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 10
cost_tier: low
---
# Kling 2.0
"""


def write_card(tmp_path, text, name="kling-2.0.md"):
    d = tmp_path / "video"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_load_and_find_card(tmp_path):
    kdir = write_card(tmp_path, CARD)
    card = find_card(kdir, "kling-2.0")
    assert card["supports_start_end_frame"] is True
    assert card["max_clip_seconds"] == 10


def test_find_unknown_model_raises(tmp_path):
    kdir = write_card(tmp_path, CARD)
    with pytest.raises(ModelError, match="no knowledge card"):
        find_card(kdir, "sora-99")


def test_validate_ok_for_verified_card(tmp_path):
    card = load_card(write_card(tmp_path, CARD) / "video" / "kling-2.0.md")
    assert validate_video_model(card, segment_seconds=5) == []


def test_validate_flags_problems(tmp_path):
    bad = CARD.replace("supports_start_end_frame: true",
                       "supports_start_end_frame: false") \
              .replace("status: verified", "status: skeleton") \
              .replace("max_clip_seconds: 10", "max_clip_seconds: 4")
    card = load_card(write_card(tmp_path, bad) / "video" / "kling-2.0.md")
    problems = validate_video_model(card, segment_seconds=5)
    assert len(problems) == 3  # нет start/end, клип короче отрезка, карточка-скелет


def test_unclosed_frontmatter_raises_model_error(tmp_path):
    kdir = write_card(tmp_path, "---\nid: x\ntype: video\nstatus: verified\n", name="bad.md")
    with pytest.raises(ModelError, match="not closed"):
        load_card(kdir / "video" / "bad.md")


def test_empty_frontmatter_raises_model_error(tmp_path):
    kdir = write_card(tmp_path, "---\n---\nbody\n", name="bad.md")
    with pytest.raises(ModelError, match="not a YAML mapping"):
        load_card(kdir / "video" / "bad.md")


def test_invalid_yaml_raises_model_error(tmp_path):
    kdir = write_card(tmp_path, "---\nkey: [unclosed\n---\nbody\n", name="bad.md")
    with pytest.raises(ModelError, match="invalid YAML"):
        load_card(kdir / "video" / "bad.md")


def test_find_card_skips_malformed_and_finds_valid(tmp_path):
    kdir = write_card(tmp_path, "---\nid: broken\n", name="aaa-broken.md")  # без закрывающего ---
    write_card(tmp_path, CARD)  # валидная kling-2.0 (сортировка: aaa-broken первым)
    card = find_card(kdir, "kling-2.0")
    assert card["id"] == "kling-2.0"


def test_find_card_mentions_skipped_when_not_found(tmp_path):
    kdir = write_card(tmp_path, "---\nid: broken\n", name="aaa-broken.md")
    with pytest.raises(ModelError, match="skipped malformed"):
        find_card(kdir, "kling-2.0")


# --- Тесты сетки допустимых длительностей (allowed_durations) ---

CARD_WITH_GRID = """---
id: seedance1_5
type: video
family: seedance
status: verified
supports_start_end_frame: true
native_audio: true
max_clip_seconds: 12
allowed_durations: [4, 8, 12]
cost_tier: low
---
# Seedance 1.5 Pro
"""

CARD_WITHOUT_GRID = """---
id: wan2_7
type: video
family: wan
status: verified
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 30
cost_tier: low
---
# Wan 2.7
"""


def test_validate_rejects_segment_not_in_allowed_grid(tmp_path):
    """segment_seconds=5 не входит в сетку [4,8,12] — ровно одна problem."""
    card = load_card(write_card(tmp_path, CARD_WITH_GRID) / "video" / "kling-2.0.md")
    problems = validate_video_model(card, segment_seconds=5)
    assert len(problems) == 1
    assert "allowed grid" in problems[0]


def test_validate_accepts_segment_in_allowed_grid(tmp_path):
    """segment_seconds=8 входит в сетку [4,8,12] — problems нет."""
    card = load_card(write_card(tmp_path, CARD_WITH_GRID) / "video" / "kling-2.0.md")
    problems = validate_video_model(card, segment_seconds=8)
    assert problems == []


def test_validate_no_grid_field_means_no_check(tmp_path):
    """Карточка без allowed_durations — поведение не меняется, problems нет."""
    card = load_card(write_card(tmp_path, CARD_WITHOUT_GRID) / "video" / "kling-2.0.md")
    problems = validate_video_model(card, segment_seconds=5)
    assert problems == []


def test_validate_audio_model_ok():
    from factory.models import validate_audio_model
    card = {"id": "inworld_text_to_speech", "type": "audio", "status": "verified"}
    assert validate_audio_model(card) == []


def test_validate_audio_model_wrong_type():
    from factory.models import validate_audio_model
    card = {"id": "kling3_0", "type": "video", "status": "verified"}
    assert any("not an audio model" in p for p in validate_audio_model(card))


def test_validate_audio_model_skeleton():
    from factory.models import validate_audio_model
    card = {"id": "sonilo_music", "type": "audio", "status": "skeleton"}
    assert any("skeleton" in p for p in validate_audio_model(card))


# --- estimate_media_cost (смета под провайдера/разрешение/тип цены) ---

SCALED_CARD = {
    "id": "seedance_2_0", "type": "video", "status": "verified",
    "providers": {
        "wavespeed": {"pricing": "scaled", "res_mult": {"720p": 1.0, "1080p": 1.4},
                      "tiers": {"fast": {"id": "wsp/seedance-fast", "usd_per_sec": 0.10}},
                      "default_tier": "fast"},
        "runware": {"pricing": "scaled", "res_mult": {"720p": 1.0, "1080p": 2.25},
                    "tiers": {"fast": {"id": "rw/seedance@2.0", "usd_per_sec": 0.13}},
                    "default_tier": "fast"},
    },
}

FLAT_CARD = {
    "id": "kling3_0", "type": "video", "status": "verified",
    "providers": {
        "wavespeed": {"pricing": "flat",
                      "tiers": {"std": {"id": "wsp/kling3-std", "usd_per_sec": 0.084},
                                "pro": {"id": "wsp/kling3-pro", "usd_per_sec": 0.168}},
                      "default_tier": "std"},
    },
}

IMAGE_CARD = {
    "id": "z_image_turbo", "type": "image", "status": "verified",
    "providers": {"wavespeed": {"id": "wsp/z-image", "pricing": "flat",
                                "usd_per_image": 0.005}},
}


def test_estimate_scaled_720p_base():
    """720p scaled = usd_per_sec × duration (res_mult 1.0)."""
    assert estimate_media_cost(SCALED_CARD, "wavespeed", "720p", 5) == pytest.approx(0.50)


def test_estimate_scaled_1080p_wavespeed_x14():
    """1080p WaveSpeed = база720p × 1.4."""
    assert estimate_media_cost(SCALED_CARD, "wavespeed", "1080p", 5) == pytest.approx(0.70)


def test_estimate_scaled_1080p_runware_x225():
    """1080p Runware = база720p × 2.25."""
    assert estimate_media_cost(SCALED_CARD, "runware", "1080p", 5) == pytest.approx(0.13 * 5 * 2.25)


def test_estimate_flat_resolution_independent():
    """flat: цена не зависит от разрешения."""
    at_720 = estimate_media_cost(FLAT_CARD, "wavespeed", "720p", 5)
    at_1080 = estimate_media_cost(FLAT_CARD, "wavespeed", "1080p", 5)
    assert at_720 == at_1080 == pytest.approx(0.42)


def test_estimate_flat_tier_selects_price():
    """Явный тир выбирает свою цену (pro дороже std)."""
    assert estimate_media_cost(FLAT_CARD, "wavespeed", "720p", 5, tier="pro") == pytest.approx(0.84)


def test_estimate_image_flat_per_image():
    """image: usd_per_image, не зависит от длительности/разрешения."""
    assert estimate_media_cost(IMAGE_CARD, "wavespeed", "1080p", 99) == pytest.approx(0.005)


def test_estimate_unknown_provider_raises():
    with pytest.raises(ModelError, match="provider"):
        estimate_media_cost(SCALED_CARD, "openrouter", "720p", 5)


# --- Аудит 2026-06-16: добитые ветки ошибок estimate_media_cost ---

def test_estimate_unknown_tier_raises():
    """Явный несуществующий тир → ModelError (а не молчаливый дефолт)."""
    with pytest.raises(ModelError, match="unknown tier"):
        estimate_media_cost(SCALED_CARD, "wavespeed", "720p", 5, tier="ultra")


def test_estimate_scaled_missing_res_mult_raises():
    """scaled без множителя под запрошенное разрешение → ModelError."""
    card = {"id": "x", "type": "video", "status": "verified",
            "providers": {"wavespeed": {
                "pricing": "scaled", "res_mult": {"720p": 1.0},
                "tiers": {"fast": {"id": "a", "usd_per_sec": 0.1}},
                "default_tier": "fast"}}}
    with pytest.raises(ModelError, match="res_mult"):
        estimate_media_cost(card, "wavespeed", "1080p", 5)


def test_estimate_missing_usd_per_sec_raises():
    """Видео-карточка без usd_per_sec → ModelError (нет базовой цены)."""
    card = {"id": "x", "type": "video", "status": "verified",
            "providers": {"wavespeed": {
                "pricing": "flat", "tiers": {"std": {"id": "a"}}, "default_tier": "std"}}}
    with pytest.raises(ModelError, match="usd_per_sec"):
        estimate_media_cost(card, "wavespeed", "720p", 5)


def test_estimate_image_missing_price_raises():
    """image-карточка без usd_per_image → ModelError."""
    card = {"id": "x", "type": "image", "status": "verified",
            "providers": {"wavespeed": {"id": "a"}}}
    with pytest.raises(ModelError, match="usd_per_image"):
        estimate_media_cost(card, "wavespeed", "720p", 0)


# --- validate_video_model под выбранного провайдера ---

PROVIDER_CARD = {
    "id": "vidu_q2_turbo", "type": "video", "status": "verified",
    "providers": {
        "runware": {"supports_start_end": True, "pricing": "scaled",
                    "allowed_durations": [4, 8], "res_mult": {"720p": 1.0, "1080p": 2.25},
                    "id": "rw/vidu-q2t", "usd_per_sec": 0.021},
        "wavespeed": {"supports_start_end": False, "pricing": "scaled",
                      "res_mult": {"720p": 1.0, "1080p": 1.4},
                      "id": "wsp/vidu-q2t", "usd_per_sec": 0.03},
    },
}


def test_validate_provider_ok():
    """Провайдер поддерживает start/end и длительность в сетке — без проблем."""
    assert validate_video_model(PROVIDER_CARD, segment_seconds=8, provider="runware") == []


def test_validate_provider_no_start_end_flagged():
    """У wavespeed нет start/end — проблема под этим провайдером."""
    problems = validate_video_model(PROVIDER_CARD, segment_seconds=5, provider="wavespeed")
    assert any("start/end" in p for p in problems)


def test_validate_provider_duration_not_in_grid():
    """5с не входит в сетку [4,8] провайдера runware."""
    problems = validate_video_model(PROVIDER_CARD, segment_seconds=5, provider="runware")
    assert any("allowed grid" in p for p in problems)


def test_validate_provider_missing_in_card():
    """Модель не заявлена для openrouter — проблема (нет в карте провайдеров)."""
    problems = validate_video_model(PROVIDER_CARD, segment_seconds=8, provider="openrouter")
    assert any("openrouter" in p for p in problems)


def test_validate_legacy_toplevel_when_no_providers_map():
    """Карта без providers + provider задан → фолбэк на top-level поля (legacy)."""
    legacy = {"id": "kling-2.0", "type": "video", "status": "verified",
              "supports_start_end_frame": True, "max_clip_seconds": 10}
    assert validate_video_model(legacy, segment_seconds=5, provider="wavespeed") == []


# --- validate_image_model: гейт трат для раскадровки (симметрично видео) ---

IMAGE_PROVIDER_CARD = {
    "id": "z_image", "type": "image", "status": "verified",
    "providers": {"wavespeed": {"id": "wsp/z", "usd_per_image": 0.005}},
}


def test_validate_image_ok():
    """Verified image-карточка под её провайдером — без проблем."""
    from factory.models import validate_image_model
    assert validate_image_model(IMAGE_PROVIDER_CARD, provider="wavespeed") == []


def test_validate_image_wrong_type():
    """Не-image карточка → проблема."""
    from factory.models import validate_image_model
    card = {"id": "x", "type": "video", "status": "verified"}
    assert any("not an image model" in p for p in validate_image_model(card))


def test_validate_image_not_on_provider():
    """Модель не заявлена под выбранного провайдера → проблема."""
    from factory.models import validate_image_model
    problems = validate_image_model(IMAGE_PROVIDER_CARD, provider="runware")
    assert any("runware" in p for p in problems)


def test_validate_image_skeleton_flagged():
    """skeleton image-карточка → проблема (гейт трат до живого спайка)."""
    from factory.models import validate_image_model
    card = {**IMAGE_PROVIDER_CARD, "status": "skeleton"}
    assert any("skeleton" in p for p in validate_image_model(card, provider="wavespeed"))
