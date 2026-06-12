import pytest
from factory.models import find_card, load_card, validate_video_model, ModelError

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
