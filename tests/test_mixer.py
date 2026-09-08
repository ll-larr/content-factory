"""Микшер: громкости дорожек, герои, дакинг и мастеринг из панели.

Значения по умолчанию добыты живыми прослушиваниями, и комментарии к ним стоят
рядом с числами в `montage.py`. Проверяется, что панель их читает и пишет ТЕМ ЖЕ
кодом, каким их читает монтажный лист, — иначе сведение на экране и сведение в
рендере разойдутся.
"""
import json
from pathlib import Path

import pytest

from factory import montage, webapp
from factory.project import load_project

BRIEF = {
    "name": "маяк", "type": "animated_series", "theme": "маяк",
    "audience": "6-9", "episodes": 1, "episode_duration_sec": 60,
    "language": "ru",
    "models": {"image": {"model": "flux_2_klein", "provider": "runware"},
               "video": {"model": "vidu_q2_turbo", "provider": "runware"}},
}


@pytest.fixture
def project(tmp_path):
    pdir = tmp_path / "маяк"
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps(BRIEF, ensure_ascii=False), encoding="utf-8")
    (pdir / "episodes" / "ep01" / "script.md").write_text(
        "---\nkind: script\nstatus: draft\ncharacters: [Устинья, Гвоздь]\n---\n"
        "текст\n", encoding="utf-8")
    return pdir


def _loaded(project):
    return load_project(project / "project.json")


# --- значения по умолчанию -------------------------------------------------

def test_defaults_come_from_montage_not_from_the_panel(project):
    settings = montage.mix_settings(_loaded(project))

    assert settings["volumes"] == montage.DEFAULT_VOLUMES
    assert settings["duck"]["gain"] == montage.DUCK_GAIN
    assert settings["muted"] == []


def test_panel_shows_every_track_with_its_default(project):
    view = webapp.mixer(project)

    assert [t["id"] for t in view["tracks"]] == list(montage.TRACKS)
    for track in view["tracks"]:
        assert track["default"] == montage.DEFAULT_VOLUMES[track["id"]]


def test_speakers_come_from_the_script_cast(project):
    """Микшеру нужен состав, а состав объявлен во frontmatter сценария."""
    view = webapp.mixer(project)

    assert [s["name"] for s in view["speakers"]] == ["Устинья", "Гвоздь"]
    assert all(s["gain"] == 1.0 for s in view["speakers"])


# --- правка ----------------------------------------------------------------

def test_volume_change_lands_in_the_brief_and_in_the_edit_list(project):
    webapp.set_mixer(project, {"volumes": {"music": 0.3}})

    assert json.loads((project / "project.json").read_text("utf-8")
                      )["mix"]["volumes"]["music"] == 0.3
    assert montage.mix_settings(_loaded(project))["volumes"]["music"] == 0.3


def test_mute_is_zero_volume_not_a_dropped_track(project):
    """Выключенная дорожка не меняет длительностей: вернуть её — снять галку."""
    webapp.set_mixer(project, {"muted": ["music"]})

    settings = montage.mix_settings(_loaded(project))
    assert settings["volumes"]["music"] == 0.0
    assert settings["muted"] == ["music"]


def test_speaker_gain_multiplies_the_voice_track_not_replaces_it(project):
    webapp.set_mixer(project, {"volumes": {"voice": 0.8},
                               "speakers": {"Гвоздь": 0.5}})

    settings = montage.mix_settings(_loaded(project))
    assert settings["volumes"]["voice"] == 0.8
    assert settings["speakers"]["Гвоздь"] == 0.5


def test_duck_and_lufs_are_written(project):
    webapp.set_mixer(project, {"duck": {"gain": 0.5, "attack_ms": 200},
                               "target_lufs": -16})

    settings = montage.mix_settings(_loaded(project))
    assert settings["duck"]["gain"] == 0.5
    assert settings["duck"]["attackMs"] == 200.0
    # Спад не трогали — остаётся дефолтным, а не обнуляется правкой соседа.
    assert settings["duck"]["releaseMs"] == float(montage.DUCK_RELEASE_MS)
    assert settings["target_lufs"] == -16


def test_disabled_mastering_survives(project):
    """`target_lufs: null` — выключенный мастеринг, а не пропущенное поле."""
    data = json.loads((project / "project.json").read_text("utf-8"))
    data["target_lufs"] = None
    (project / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert montage.mix_settings(_loaded(project))["target_lufs"] is None
    assert webapp.mixer(project)["target_lufs"] is None


# --- отказы ----------------------------------------------------------------

def test_unknown_track_is_refused(project):
    with pytest.raises(webapp.WebappError):
        webapp.set_mixer(project, {"volumes": {"барабаны": 0.5}})


def test_volume_out_of_range_is_refused(project):
    for bad in (-0.1, 99, "громко", True):
        with pytest.raises(webapp.WebappError):
            webapp.set_mixer(project, {"volumes": {"music": bad}})


def test_duck_gain_above_one_is_refused(project):
    """Дакинг только приглушает: gain > 1 означал бы усиление музыки под речью."""
    with pytest.raises(webapp.WebappError):
        webapp.set_mixer(project, {"duck": {"gain": 1.5}})


def test_refusal_leaves_the_brief_readable(project):
    before = (project / "project.json").read_text("utf-8")
    with pytest.raises(webapp.WebappError):
        webapp.set_mixer(project, {"volumes": {"music": 99}})

    assert (project / "project.json").read_text("utf-8") == before
    load_project(project / "project.json")


def test_panel_and_render_read_the_same_settings(project):
    """Два набора значений — это две разные серии из одного проекта."""
    webapp.set_mixer(project, {"volumes": {"sfx": 0.25}, "muted": ["ambience"]})

    view = {t["id"]: t["volume"] for t in webapp.mixer(project)["tracks"]}
    assert view == montage.mix_settings(_loaded(project))["volumes"]


def test_mastering_can_be_switched_off_and_back_on(project):
    """Выключенный мастеринг обязан включаться обратно: иначе `null` в брифе —
    тупик, из которого панель не выводит."""
    webapp.set_mixer(project, {"target_lufs": None})
    assert webapp.mixer(project)["target_lufs"] is None

    webapp.set_mixer(project, {"target_lufs": -14})
    assert webapp.mixer(project)["target_lufs"] == -14
