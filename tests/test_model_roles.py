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


def test_skeleton_is_visible_but_not_selectable(project, tmp_path):
    """Спрятать — скрыть, что модель существует; разрешить — обойти гейт трат.

    У такой карточки блоки `providers` закрыты комментарием (правило CLAUDE.md),
    поэтому она попадает в список одной строкой без провайдера и с причиной.
    Карточка пишется в КОПИЮ knowledge: в репозитории скелетов не осталось —
    все открыты по каталогу 2026-09-12, — а поведение гейта от этого не
    изменилось.
    """
    import shutil

    kdir = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE, kdir)
    (kdir / "video" / "скелет.md").write_text('---\nid: скелет\ntype: video\nfamily: тест\nstatus: skeleton\n---\n\n# Скелет\n', encoding="utf-8")

    rows = {row["role"]: row for row in webapp.model_roles(project, kdir)}
    seen = [c for row in rows.values()
            for c in row["candidates"] if c["status"] == "skeleton"]

    assert seen, "скелет пропал из списка — значит от человека спрятали модель"
    assert all(c["selectable"] is False for c in seen)
    # Невыбираемое ВСЕГДА объясняет себя: молчаливо серая строка ничем не
    # отличается от ошибки панели.
    assert all(c["reason"] for row in rows.values()
               for c in row["candidates"] if not c["selectable"])


def test_every_role_has_something_to_choose(project):
    """У каждой роли конвейера есть хоть одна выбираемая модель.

    Роль, в которой всё серое (так было у фоли и липсинка до 2026-09-12),
    выглядит как сломанная панель: выпадающий список пуст, а почему — написано
    в свёрнутом блоке, куда не заглядывают.
    """
    for role, row in _roles(project).items():
        assert any(c["selectable"] for c in row["candidates"]), role


def test_price_says_what_it_is_for(project):
    """Число без единицы обманывает: секунда звука и кадр — разные деньги.

    До 2026-09-12 звук считался за НОЛЬ секунд, и панель показывала «$0.0000»
    у модели по цене цента за секунду. Бесплатных моделей не бывает.
    """
    roles = _roles(project)
    sfx = next(c for c in roles["audio.sfx"]["candidates"]
               if c["model"] == "mirelo_sfx_16")
    frame = next(c for c in roles["image"]["candidates"]
                 if c["model"] == "z_image_turbo")

    assert sfx["price"] > 0 and sfx["price_unit"] == "с"
    assert frame["price_unit"] == "кадр"
    assert roles["video"]["candidates"][0]["price_unit"] == "отрезок"


def test_model_that_cannot_hold_the_segment_is_not_offered(project):
    """Панель не предлагает то, что запись выбора немедленно отобьёт.

    `veo3_1` принимает 4, 6 и 8 секунд; у проекта отрезок 5 — карточка
    формально открыта, но недостижима. Раньше такую можно было выбрать и
    получить отказ уже после клика.
    """
    row = _roles(project)["video"]
    candidate = next(c for c in row["candidates"] if c["model"] == "veo3_1")

    assert candidate["selectable"] is False
    assert "5s" in candidate["reason"] or "duration" in candidate["reason"]

    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"video": {"model": "veo3_1", "provider": "wavespeed"}},
            KNOWLEDGE)


def test_one_row_per_model_at_the_cheapest_provider(project):
    """Одна модель у двух провайдеров — это два ценника, а не два выбора.

    `vidu_q2_turbo` стоит $0.11 на Runware и $0.20 на WaveSpeed; дороже берут
    ровно тогда, когда не заметили дешевле.
    """
    row = _roles(project)["video"]
    vidu = [c for c in row["candidates"] if c["model"] == "vidu_q2_turbo"]

    assert len(vidu) == 1
    assert vidu[0]["provider"] == "runware"
    models = [c["model"] for c in row["candidates"]]
    assert len(models) == len(set(models))


def test_the_current_choice_survives_even_if_it_is_dearer(project):
    """Иначе список показывал бы не то, что записано в брифе."""
    webapp.set_project_models(
        project, {"video": {"model": "vidu_q2_turbo", "provider": "wavespeed"}},
        KNOWLEDGE)
    vidu = [c for c in _roles(project)["video"]["candidates"]
            if c["model"] == "vidu_q2_turbo"]

    assert {c["provider"] for c in vidu} == {"runware", "wavespeed"}
    kept = next(c for c in vidu if c["provider"] == "wavespeed")
    assert kept["current"] is True, "вторая строка обязана назвать себя текущей"


def test_model_without_end_frame_support_is_still_offered(project):
    """Стык кадров необязателен (2026-09-03) — и выбор он не запрещает.

    Пока гейт требовал start/end всегда, панель отказывала моделям, которые
    делают ровно ту работу, какую конвейер им и даёт. Панель теперь не молчит
    об ограничении: строка помечена `start_end: False`, а откажет такой выбор
    только на плане со стыками — гейтом платной стадии, до траты.
    """
    row = _roles(project)["video"]
    candidate = next(c for c in row["candidates"]
                     if c["model"] == "grok_video_v15")

    assert candidate["start_end"] is False
    assert candidate["selectable"] is True
    webapp.set_project_models(
        project, {"video": {"model": "grok_video_v15", "provider": "wavespeed"}},
        KNOWLEDGE)


def test_image_model_without_refs_says_so(project):
    """Кадр по референсу персонажа умеет не всякая модель картинок."""
    row = _roles(project)["image"]
    grok = next(c for c in row["candidates"] if c["model"] == "grok_image")
    flux = next(c for c in row["candidates"] if c["model"] == "flux_2_klein")

    assert grok["refs"] is False and grok["selectable"] is True
    assert flux["refs"] is True


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


def test_skeleton_model_is_refused_before_it_reaches_the_brief(project, tmp_path):
    """Скелет не попадает в бриф даже прямым запросом.

    Карточка пишется в КОПИЮ knowledge: в самом репозитории видео-скелетов
    больше нет (открыты по каталогу 2026-09-12), а проверять гейт на живом
    наборе карточек значило бы отменять тест каждый раз, когда открывают
    очередную модель.
    """
    import shutil

    kdir = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE, kdir)
    (kdir / "video" / "скелет.md").write_text(
        "---\nid: скелет\ntype: video\nfamily: тест\nstatus: skeleton\nproviders:\n  wavespeed: {id: 'x/y', pricing: flat, usd_per_sec: 0.01}\n---\n\n# Скелет\n",
        encoding="utf-8")

    with pytest.raises(webapp.WebappError):
        webapp.set_project_models(
            project, {"video": {"model": "скелет", "provider": "wavespeed"}},
            kdir)
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
