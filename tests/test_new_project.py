"""Создание проекта из панели: мастер вместо project.json, набранного руками.

Пока первый бриф пишется в редакторе, «человек пользуется только панелью» —
неправда с самого первого шага.
"""
import json
from pathlib import Path

import pytest

from factory import webapp
from factory.genres import load_genre
from factory.project import load_project, type_for

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "projects").mkdir()
    return tmp_path / "projects"


def _make(root, **over):
    data = {"name": "маяк", "genre": "animation", "format": "wide_16x9",
            "theme": "смотрительница маяка", "language": "ru",
            "audience": "6-9", "episodes": 2, "episode_duration_sec": 60}
    data.update(over)
    return webapp.create_project(root, data, KNOWLEDGE)


# --- что предлагает мастер -------------------------------------------------

def test_options_come_from_genre_cards(tmp_path):
    options = webapp.new_project_options(KNOWLEDGE)

    ids = {g["id"] for g in options["genres"]}
    assert {"animation", "anime", "live_action", "educational"} <= ids
    # Форматов два: «полный метр» и «сериал» давали одну и ту же картинку и
    # различались только структурой брифа — теперь это одна кнопка, а число
    # серий человек пишет сам.
    assert {f["id"] for f in options["formats"]} == {"wide_16x9", "shorts_9x16"}
    assert {lang["id"] for lang in options["languages"]} >= {"ru", "en"}


def test_default_models_are_verified_cards(tmp_path):
    """Молчаливый дефолт тратит деньги человека: он обязан быть проверенным."""
    from factory.models import find_card

    for entry in webapp.DEFAULT_MODELS.values():
        card = find_card(KNOWLEDGE, entry["model"])
        assert str(card["status"]).startswith("verified"), entry
        assert entry["provider"] in card["providers"], entry


# --- дерево проекта --------------------------------------------------------

def test_creates_a_readable_project(root):
    result = _make(root)

    pdir = root / "маяк"
    assert (pdir / "project.json").is_file()
    assert (pdir / "manifest.json").is_file()
    assert (pdir / "bible" / "idea.md").is_file()
    assert (pdir / "episodes" / "ep01").is_dir()
    assert (pdir / "episodes" / "ep02").is_dir()
    project = load_project(pdir / "project.json")
    assert project.genre == "animation" and project.format == "wide_16x9"
    assert "project.json" in result["created"]


def test_legacy_type_is_derived_not_asked(root):
    """`type` набранный руками однажды разойдётся с жанром, и никто не заметит."""
    _make(root)
    data = json.loads((root / "маяк" / "project.json").read_text("utf-8"))

    assert data["type"] == type_for(load_genre(KNOWLEDGE, "animation"),
                                    "wide_16x9") == "animated_series"


def test_educational_project_gets_stills_by_default(root):
    _make(root, name="космос", genre="educational", audience="12+")

    project = load_project(root / "космос" / "project.json")
    assert project.visual_mode == "stills"
    assert project.genre_card(KNOWLEDGE)["fact_check"] == "required"


def test_shorts_asks_duration_instead_of_episodes(root):
    _make(root, name="шортс", format="shorts_9x16", duration_sec=45,
          episodes=None, episode_duration_sec=None)

    data = json.loads((root / "шортс" / "project.json").read_text("utf-8"))
    assert data["duration_sec"] == 45
    assert "episodes" not in data


def test_old_format_name_is_accepted_and_normalised(root):
    """Бриф, набитый по прошлой документации, не должен отбиваться."""
    _make(root, name="старый", format="series_16x9")

    project = load_project(root / "старый" / "project.json")
    assert project.format == "wide_16x9"


def test_one_episode_is_a_normal_project(root):
    """«Полный метр» — это сериал из одной серии, и он обязан заводиться."""
    _make(root, name="метр", episodes=1, episode_duration_sec=600)

    project = load_project(root / "метр" / "project.json")
    assert project.raw["episodes"] == 1
    assert (root / "метр" / "episodes" / "ep01").is_dir()
    assert not (root / "метр" / "episodes" / "ep02").exists()


def test_manifest_is_created_empty_right_away(root):
    """«Проект есть, памяти нет» — состояние, в котором панель ничего не покажет."""
    _make(root)
    assert json.loads(
        (root / "маяк" / "manifest.json").read_text("utf-8")) == {"items": {}}


# --- отказы ----------------------------------------------------------------

def test_refuses_a_name_that_escapes_the_projects_root(root):
    with pytest.raises(webapp.WebappError):
        _make(root, name="../секреты")


def test_refuses_an_existing_project(root):
    _make(root)
    with pytest.raises(webapp.WebappError):
        _make(root)


def test_refuses_an_empty_theme(root):
    """Тема — вход всей первой половины конвейера, пустой она быть не может."""
    with pytest.raises(webapp.WebappError):
        _make(root, theme="   ")


def test_refuses_an_unknown_genre(root):
    with pytest.raises(webapp.WebappError):
        _make(root, genre="дорама")


def test_refuses_an_unknown_format(root):
    with pytest.raises(webapp.WebappError):
        _make(root, format="квадрат")


def test_refuses_a_visual_mode_the_genre_forbids(root):
    """У мультфильма режима «кадры» нет: слайдшоу вместо мультика — не экономия."""
    with pytest.raises(webapp.WebappError):
        _make(root, visual_mode="stills")


def test_refuses_animated_project_without_audience(root):
    with pytest.raises(webapp.WebappError):
        _make(root, audience="")


def test_refuses_nonsense_episode_count(root):
    for bad in (0, -3, "много", 10_000):
        with pytest.raises(webapp.WebappError):
            _make(root, name=f"проект-{bad}", episodes=bad)


def test_nothing_is_left_behind_after_a_refusal(root):
    with pytest.raises(webapp.WebappError):
        _make(root, name="битый", episodes="много")
    assert not (root / "битый").exists()


# --- легаси-тип выводится, а не набирается ---------------------------------

def test_every_genre_card_declares_whether_it_is_drawn():
    """От `animated` зависит выведенный `type`, а от типа — поля брифа."""
    from factory.genres import all_genres

    for card in all_genres(KNOWLEDGE):
        assert isinstance(card["animated"], bool), card["id"]


def test_type_for_covers_every_genre_and_format():
    from factory.genres import all_genres
    from factory.project import FORMAT_ASPECT, REQUIRED_BY_TYPE

    for card in all_genres(KNOWLEDGE):
        for fmt in FORMAT_ASPECT:
            assert type_for(card, fmt) in REQUIRED_BY_TYPE, (card["id"], fmt)


def test_type_for_refuses_an_unknown_format():
    from factory.project import ProjectError

    with pytest.raises(ProjectError):
        type_for(load_genre(KNOWLEDGE, "animation"), "квадрат")


def test_shorts_never_gets_an_animated_type():
    """`animated_shorts` в легаси-типах не было: жанр живёт в поле genre."""
    for genre in ("animation", "anime", "educational", "live_action"):
        assert type_for(load_genre(KNOWLEDGE, genre), "shorts_9x16") == "shorts"
