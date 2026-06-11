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
