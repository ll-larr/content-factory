"""Карточки жанров: чем познавательный ролик отличается от мультфильма.

Жанр — данные, а не строка в конфиге. Пока различия жили в головах и в скиллах,
каждая новая стадия писалась дважды: отдельно для повествования, отдельно для
всего остального.
"""
from pathlib import Path

import pytest

from factory import genres
from factory.models import ModelError, find_card

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


def test_all_declared_genres_load():
    ids = {g["id"] for g in genres.all_genres(KNOWLEDGE)}
    assert ids == {"animation", "anime", "live_action", "educational"}


def test_unknown_genre_names_the_known_ones():
    with pytest.raises(genres.GenreError) as e:
        genres.load_genre(KNOWLEDGE, "детектив")
    assert "educational" in str(e.value)


def test_educational_has_no_characters_stage():
    """У познавательного нет персонажей — значит нет и стадии про них."""
    card = genres.load_genre(KNOWLEDGE, "educational")
    assert "characters" not in card["stages"]
    assert card["has_characters"] is False
    assert card["narrator"] is True


def test_animation_keeps_characters():
    card = genres.load_genre(KNOWLEDGE, "animation")
    assert "characters" in card["stages"]
    assert card["has_characters"] is True


def test_educational_forbids_lipsync():
    """Губ в кадре нет: стадия недоступна и платить за неё не за что."""
    assert genres.load_genre(KNOWLEDGE, "educational")["lipsync"] is False
    assert genres.load_genre(KNOWLEDGE, "animation")["lipsync"] is True


def test_educational_requires_research_and_fact_check():
    card = genres.load_genre(KNOWLEDGE, "educational")
    assert card["requires_research"] is True
    assert card["fact_check"] == "required"


def test_narrative_genres_do_not_demand_fact_check():
    for genre in ("animation", "anime", "live_action"):
        assert genres.load_genre(KNOWLEDGE, genre)["fact_check"] == "none"


def test_default_visual_mode_is_among_allowed():
    for card in genres.all_genres(KNOWLEDGE):
        assert card["default_visual_mode"] in card["visual_modes"], card["id"]


def test_stages_are_known_pipeline_stages():
    """Опечатка в карточке не должна порождать стадию-призрак."""
    for card in genres.all_genres(KNOWLEDGE):
        for stage in card["stages"]:
            assert stage in genres.KNOWN_STAGES, (card["id"], stage)


def test_broken_card_is_rejected_with_its_path(tmp_path):
    (tmp_path / "genres").mkdir()
    (tmp_path / "genres" / "битый.md").write_text(
        "---\nid: битый\n---\n", encoding="utf-8")
    with pytest.raises(genres.GenreError) as e:
        genres.load_genre(tmp_path, "битый")
    assert "битый.md" in str(e.value)


def test_genre_cards_do_not_break_model_lookup():
    """Карточки жанров лежат в том же knowledge/, но моделями не притворяются."""
    with pytest.raises(ModelError) as e:
        find_card(KNOWLEDGE, "нет-такой-модели")
    assert "genres" not in str(e.value)


def test_shot_language_tells_storyboard_how_to_speak():
    assert genres.load_genre(KNOWLEDGE, "educational")["shot_language"] == "schema"
    assert genres.load_genre(KNOWLEDGE, "animation")["shot_language"] == "cinematic"


def test_stills_allowed_only_where_declared():
    """Режим кадров — не универсальная экономия: кино им не снимают."""
    assert "stills" in genres.load_genre(KNOWLEDGE, "educational")["visual_modes"]
    assert genres.load_genre(KNOWLEDGE, "educational")["default_visual_mode"] == "stills"
    assert genres.load_genre(KNOWLEDGE, "animation")["default_visual_mode"] == "video"
