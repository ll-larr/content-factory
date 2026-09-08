"""Выбор моделей по ролям из панели.

Это последнее, что заставляло править project.json руками. Проверяется не
«список показался», а то, что панель не даёт записать модель, на которой съёмка
потом откажет, и не прячет от человека существующие, но неподтверждённые.
"""
import json
from pathlib import Path

import pytest

from factory import webapp

REPO = Path(__file__).resolve().parents[1]
KNOWLEDGE = REPO / "knowledge"

BRIEF = {
    "name": "маяк", "type": "animated_series", "genre": "animation",
    "format": "wide_16x9", "theme": "маяк", "audience": "6-9",
    "episodes": 1, "episode_duration_sec": 60, "language": "ru",
    "models": {"image": {"model": "flux_2_klein", "provider": "runware"},
               "video": {"model": "vidu_q2_turbo", "provider": "runware"}},
}


@pytest.fixture
def project(tmp_path):
    pdir = tmp_path / "маяк"
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps(BRIEF, ensure_ascii=False), encoding="utf-8")
    return pdir


def _roles(project):
    return {row["role"]: row for row in webapp.model_roles(project, KNOWLEDGE)}


# --- что показано ----------------------------------------------------------

def test_every_role_of_the_pipeline_is_offered(project):
    roles = _roles(project)
    assert set(roles) == set(webapp.MODEL_ROLES)


def test_current_choice_comes_from_the_brief(project):
    roles = _roles(project)

    assert roles["image"]["current"]["model"] == "flux_2_klein"
    assert roles["video"]["current"]["provider"] == "runware"


def test_unset_role_is_empty_not_an_error(project):
    """Проект без звука валиден: эпизод просто собирается молча."""
    assert _roles(project)["audio.tts"]["current"]["model"] is None


def test_candidates_match_the_role_kind(project):
    from factory.models import find_card

    for role, row in _roles(project).items():
        spec = webapp.MODEL_ROLES[role]
        for candidate in row["candidates"]:
            card = find_card(KNOWLEDGE, candidate["model"])
            assert card["type"] == spec["type"], candidate
            if spec["kind"]:
                assert card["audio_kind"] == spec["kind"], candidate


def test_skeleton_is_visible_but_not_selectable(project):
    """Спрятать — скрыть, что модель существует; разрешить — обойти гейт трат.

    У такой карточки блоки `providers` закрыты комментарием (правило CLAUDE.md),
    поэтому она попадает в список одной строкой без провайдера и с причиной.
    """
    seen = [c for row in _roles(project).values()
            for c in row["candidates"] if c["status"] == "skeleton"]

    assert seen, "в knowledge нет ни одной skeleton-карточки — тест бессмыслен"
    assert all(c["selectable"] is False for c in seen)
    assert all(c["reason"] for c in seen)
    # Невыбираемое ВСЕГДА объясняет себя: молчаливо серая строка ничем не
    # отличается от ошибки панели.
    assert all(c["reason"] for row in _roles(project).values()
               for c in row["candidates"] if not c["selectable"])


def test_model_that_cannot_hold_the_segment_is_not_offered(project):
    """Панель не предлагает то, что запись выбора немедленно отобьёт.

    `veo3_1_lite` принимает 4, 6 и 8 секунд; у проекта отрезок 5 — карточка
    формально открыта, но недостижима. Раньше такую можно было выбрать и
    получить отказ уже после клика.
    """
    row = _roles(project)["video"]
    candidate = next(c for c in row["candidates"]
                     if c["model"] == "veo3_1_lite")

    assert candidate["selectable"] is False
    assert "5s" in candidate["reason"] or "duration" in candidate["reason"]

    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"video": {"model": "veo3_1_lite", "provider": "openrouter"}},
            KNOWLEDGE)


def test_the_same_verdict_answers_both_questions(project):
    """Список и запись спрашивают ОДНУ функцию: два ответа разошлись бы (D-3)."""
    for row in _roles(project).values():
        for c in row["candidates"]:
            if not c["provider"]:
                continue
            choice = {row["role"]: {"model": c["model"],
                                    "provider": c["provider"]}}
            if c["selectable"]:
                continue
            with pytest.raises(webapp.WebappError):
                webapp.set_project_models(project, choice, KNOWLEDGE)


def test_price_is_counted_for_this_project(project):
    """Цена в выборе и цена в смете — одно число, иначе выбор по цене врёт."""
    from factory.models import estimate_media_cost, find_card
    from factory.project import load_project

    loaded = load_project(project / "project.json")
    row = _roles(project)["video"]
    candidate = next(c for c in row["candidates"]
                     if c["model"] == "vidu_q2_turbo" and c["provider"] == "runware")

    card = find_card(KNOWLEDGE, "vidu_q2_turbo")
    assert candidate["price"] == estimate_media_cost(
        card, "runware", loaded.resolution, loaded.segment_seconds,
        (card["providers"]["runware"]).get("default_tier"))


def test_native_audio_is_reported_for_video_models(project):
    row = _roles(project)["video"]
    assert any(c["native_audio"] for c in row["candidates"])
    assert any(not c["native_audio"] for c in row["candidates"])


def test_lipsync_role_is_hidden_where_the_genre_forbids_it(tmp_path):
    """Тот же ответ, что даёт лестница стадий: губ в кадре нет — платить не за что."""
    pdir = tmp_path / "познавательный"
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    brief = dict(BRIEF, name="познавательный", genre="educational")
    (pdir / "project.json").write_text(
        json.dumps(brief, ensure_ascii=False), encoding="utf-8")

    assert "audio.lipsync" not in _roles(pdir)


# --- что записывается ------------------------------------------------------

def test_writing_a_choice_updates_the_brief(project):
    webapp.set_project_models(
        project, {"image": {"model": "z_image_turbo", "provider": "wavespeed"}},
        KNOWLEDGE)

    data = json.loads((project / "project.json").read_text("utf-8"))
    assert data["models"]["image"] == {"model": "z_image_turbo",
                                       "provider": "wavespeed"}


def test_audio_role_lands_under_models_audio(project):
    webapp.set_project_models(
        project,
        {"audio.tts": {"model": "gemini_2_5_pro_tts", "provider": "wavespeed"}},
        KNOWLEDGE)

    data = json.loads((project / "project.json").read_text("utf-8"))
    assert data["models"]["audio"]["tts"]["model"] == "gemini_2_5_pro_tts"


def test_skeleton_model_is_refused_before_it_reaches_the_brief(project):
    from factory.models import all_cards

    skeleton = next(c for c in all_cards(KNOWLEDGE)
                    if c["type"] == "video"
                    and str(c["status"]).startswith("skeleton"))

    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"video": {"model": skeleton["id"], "provider": "wavespeed"}},
            KNOWLEDGE)
    data = json.loads((project / "project.json").read_text("utf-8"))
    assert data["models"]["video"]["model"] == "vidu_q2_turbo"


def test_model_on_a_provider_that_does_not_declare_it_is_refused(project):
    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"image": {"model": "flux_2_klein", "provider": "нетакой"}},
            KNOWLEDGE)


def test_image_model_cannot_be_put_into_the_video_role(project):
    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"video": {"model": "flux_2_klein", "provider": "runware"}},
            KNOWLEDGE)


def test_music_model_cannot_be_put_into_the_voice_role(project):
    """Подмена роли вскрылась бы только на слух, уже после оплаты."""
    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project,
            {"audio.tts": {"model": "sonilo_music", "provider": "wavespeed"}},
            KNOWLEDGE)


def test_unknown_role_never_becomes_a_key_in_the_brief(project):
    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(project, {"../побег": {"model": "x",
                                                        "provider": "y"}},
                                  KNOWLEDGE)
    assert "../побег" not in json.loads(
        (project / "project.json").read_text("utf-8"))["models"]


def test_refusal_leaves_the_brief_readable(project):
    before = (project / "project.json").read_text("utf-8")
    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(project, {"image": {"model": "нет-такой",
                                                      "provider": "runware"}},
                                  KNOWLEDGE)
    assert (project / "project.json").read_text("utf-8") == before
