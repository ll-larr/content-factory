"""Тесты монтажного листа (спека 2026-08-31 §4).

Лист — намерение, а не факты о медиа: ни одной длительности он не содержит,
ни один тест здесь не читает медиафайлы. Длительности, fps и размеры выясняет
Remotion (`parseMedia`), их раскладка проверяется на стороне Node.
"""
import json
from pathlib import Path

import pytest

from factory import montage
from factory.manifest import Manifest
from factory.project import load_project
from factory.shots import load_shots

PROJECT = {
    "name": "pilot", "type": "animated_series",
    "theme": "Смотрительница маяка: две серии о том, как гаснет свет",
    "audience": "9-12", "episodes": 1, "episode_duration_sec": 10,
    "language": "ru",
    "models": {"image": "nano_banana_flash", "video": "kling3_0"},
}
SHOTS = {
    "episode": "ep01",
    "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
               {"n": 3, "prompt": "c"}],
    "segments": [{"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
                 {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
}
AUDIO = {
    "voice_lines": [
        {"id": "v1", "segment": 2, "offset": 1.5, "speaker": "Устинья",
         "voice": "warm", "text": "Свет погас."}],
    "sfx": [{"id": "s1", "segment": 1, "offset": 3.0, "prompt": "wind",
             "duration": 0.8}],
    "music_cues": [{"id": "m1", "segment": 1, "offset": 0.0, "prompt": "sea",
                    "duration": 10.0}],
}


def _accept(manifest, item_id, kind, file=None):
    """Провести единицу до done легальным путём переходов манифеста."""
    manifest.add(item_id, kind=kind)
    manifest.set_status(item_id, "generating")
    manifest.set_status(item_id, "generated", file=file)
    manifest.set_status(item_id, "done")


@pytest.fixture
def proj(tmp_path, monkeypatch):
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    (ep / "segments").mkdir(parents=True)
    (ep / "audio").mkdir(parents=True)
    (pdir / "project.json").write_text(
        json.dumps(PROJECT, ensure_ascii=False), encoding="utf-8")
    (ep / "shots.json").write_text(
        json.dumps(SHOTS, ensure_ascii=False), encoding="utf-8")
    (ep / "audio.json").write_text(
        json.dumps(AUDIO, ensure_ascii=False), encoding="utf-8")
    for n in (1, 2):
        (ep / "segments" / f"{n:03d}.mp4").write_bytes(b"stub")

    m = Manifest(pdir / "manifest.json")
    for n in (1, 2):
        _accept(m, f"ep01/segments/{n:03d}", "segment")
    for eid, kind in (("v1", "voice"), ("s1", "sfx"), ("m1", "music")):
        f = ep / "audio" / f"{eid}.mp3"
        f.write_bytes(b"stub")
        _accept(m, f"ep01/audio/{eid}", kind, file=str(f))
    m.save()
    monkeypatch.chdir(tmp_path)
    return pdir


def _load(pdir):
    ep = pdir / "episodes" / "ep01"
    return (load_project(pdir / "project.json"),
            load_shots(ep / "shots.json", pdir),
            Manifest(pdir / "manifest.json"))


def _build(pdir, fmt="16x9"):
    project, shots, manifest = _load(pdir)
    return montage.build_edit_list(
        project=project, project_dir=pdir, episode="ep01",
        shots=shots, manifest=manifest, fmt=fmt,
        knowledge_dir=Path(__file__).resolve().parents[1] / "knowledge")


# --- гейт ревью -------------------------------------------------------------

def test_review_problems_empty_when_everything_accepted(proj):
    project, shots, manifest = _load(proj)
    plan = montage.load_plan(proj / "episodes" / "ep01", shots)
    assert montage.review_problems(manifest, "ep01", shots, plan) == {}


def test_review_problems_merges_segments_and_audio(proj):
    """Один список на оба гейта: прежде это были два разных скрипта."""
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/segments/002", "pending")
    del m.data["items"]["ep01/audio/v1"]
    m.save()

    project, shots, manifest = _load(proj)
    plan = montage.load_plan(proj / "episodes" / "ep01", shots)
    assert montage.review_problems(manifest, "ep01", shots, plan) == {
        "ep01/segments/002": "статус pending",
        "ep01/audio/v1": "не генерировался",
    }


# --- построение листа -------------------------------------------------------

def test_edit_list_keeps_segment_offset_coordinates(proj):
    """segment+offset переносятся как есть: систему координат меняет только Node."""
    lst = _build(proj)
    assert lst["voice"] == [{
        "id": "v1", "file": "episodes/ep01/audio/v1.mp3",
        "segment": 2, "offset": 1.5, "volume": 1.0, "text": "Свет погас."}]
    # уровни пересмотрены 2026-09-05: событие 0.5, подложка 0.16 —
    # на прежних 0.7 непрерывное море перекрывало речь
    assert lst["sfx"][0]["volume"] == montage.SFX_VOLUME
    assert lst["music"][0]["volume"] == montage.MUSIC_VOLUME


def test_edit_list_segments_ordered_and_relative_to_project(proj):
    lst = _build(proj)
    assert lst["segments"] == [
        {"n": 1, "file": "episodes/ep01/segments/001.mp4"},
        {"n": 2, "file": "episodes/ep01/segments/002.mp4"}]


def test_edit_list_carries_no_durations(proj):
    """Ни одной длительности: иначе две стороны читали бы медиа врозь."""
    blob = json.dumps(_build(proj))
    assert "duration" not in blob
    assert "fps" not in blob


def test_edit_list_expected_block_from_project(proj):
    lst = _build(proj)
    assert lst["expected"] == {
        "segments": 2, "segmentSeconds": 5, "tolerance": 0.05}


def test_edit_list_duck_constants(proj):
    """Параметры подавления идут в лист из констант, а не зашиты в монтаж.

    Значения выбраны на слух и пересмотрены 2026-09-05: слышимый рывок давала
    мгновенная атака, а не глубина.
    """
    assert _build(proj)["duck"] == {
        "gain": montage.DUCK_GAIN, "attackMs": montage.DUCK_ATTACK_MS,
        "releaseMs": montage.DUCK_RELEASE_MS}


def test_missing_files_reported_all_at_once(proj):
    (proj / "episodes/ep01/segments/001.mp4").unlink()
    (proj / "episodes/ep01/audio/m1.mp3").unlink()
    with pytest.raises(montage.MontageError) as e:
        _build(proj)
    text = str(e.value)
    assert "001.mp4" in text and "m1.mp3" in text


def test_file_outside_project_dir_is_refused(proj, tmp_path):
    stray = tmp_path / "stray.mp3"
    stray.write_bytes(b"stub")
    m = Manifest(proj / "manifest.json")
    m.data["items"]["ep01/audio/v1"]["file"] = str(stray)
    m.save()
    with pytest.raises(montage.MontageError) as e:
        _build(proj)
    assert "stray.mp3" in str(e.value)


def test_unknown_format_is_refused(proj):
    with pytest.raises(montage.MontageError):
        _build(proj, fmt="4x3")


def test_missing_audio_plan_gives_empty_tracks(proj):
    (proj / "episodes/ep01/audio.json").unlink()
    lst = _build(proj)
    assert lst["voice"] == [] and lst["sfx"] == [] and lst["music"] == []
    assert lst["segments"]


# --- оформление шортсов -----------------------------------------------------

def test_shorts_defaults_derived_from_theme(proj):
    """Без блока shorts формат 9:16 работает: баннер — тема до двоеточия."""
    lst = _build(proj, fmt="9x16")
    assert lst["shorts"] == {
        "banner": "Смотрительница маяка",
        "background": "#101820",
        "accent": "#E8B04B"}


def test_shorts_block_overrides_defaults(proj):
    data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    data["shorts"] = {"banner": "Маяк", "accent": "#FFFFFF"}
    (proj / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    lst = _build(proj, fmt="9x16")
    assert lst["shorts"] == {
        "banner": "Маяк", "background": "#101820", "accent": "#FFFFFF"}


def test_shorts_banner_falls_back_to_project_name(proj):
    data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    data["theme"] = "—"
    (proj / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert _build(proj, fmt="9x16")["shorts"]["banner"] == "pilot"


# --- липсинк и фоли в монтажном листе (дизайн 2026-09-04 §5) ---

def test_segment_file_prefers_accepted_lipsync(proj):
    ep = proj / "episodes" / "ep01"
    (ep / "segments" / "001-lipsync.mp4").write_bytes(b"lip")
    m = Manifest(proj / "manifest.json")
    _accept(m, "ep01/lipsync/001", "lipsync")
    m.save()
    lst = _build(proj)
    assert lst["segments"][0]["file"].endswith("001-lipsync.mp4")
    # второй отрезок липсинка не получал — остаётся исходником
    assert lst["segments"][1]["file"].endswith("002.mp4")


def test_segment_file_ignores_unaccepted_lipsync(proj):
    # Липсинк сгенерирован, но не принят — берём исходник. Иначе неудачный дубль
    # молча уехал бы в финальный файл.
    ep = proj / "episodes" / "ep01"
    (ep / "segments" / "001-lipsync.mp4").write_bytes(b"lip")
    m = Manifest(proj / "manifest.json")
    m.add("ep01/lipsync/001", kind="lipsync")
    m.set_status("ep01/lipsync/001", "generating")
    m.set_status("ep01/lipsync/001", "generated")
    m.save()
    assert _build(proj)["segments"][0]["file"].endswith("001.mp4")


def test_segment_file_ignores_missing_lipsync_file(proj):
    # Приёмка есть, а файла нет: берём исходник, а не падаем и не отдаём пустоту.
    m = Manifest(proj / "manifest.json")
    _accept(m, "ep01/lipsync/001", "lipsync")
    m.save()
    assert _build(proj)["segments"][0]["file"].endswith("001.mp4")


def test_foley_track_goes_into_edit_list(proj):
    ep = proj / "episodes" / "ep01"
    plan = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    plan["foley"] = [{"id": "f1", "segment": 2, "prompt": "boots on iron"}]
    (ep / "audio.json").write_text(json.dumps(plan, ensure_ascii=False),
                                   encoding="utf-8")
    f = ep / "audio" / "f1.mp4"
    f.write_bytes(b"stub")
    m = Manifest(proj / "manifest.json")
    _accept(m, "ep01/foley/f1", "foley", file=str(f))
    m.save()
    lst = _build(proj)
    assert lst["foley"][0]["id"] == "f1"
    assert lst["foley"][0]["volume"] == montage.FOLEY_VOLUME


def test_foley_blocks_render_until_accepted(proj):
    # Фоли живёт под своим префиксом в манифесте: без приёмки монтаж стоит.
    ep = proj / "episodes" / "ep01"
    plan = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    plan["foley"] = [{"id": "f1", "segment": 2, "prompt": "boots"}]
    (ep / "audio.json").write_text(json.dumps(plan, ensure_ascii=False),
                                   encoding="utf-8")
    project, shots, manifest = _load(proj)
    problems = montage.review_problems(
        manifest, "ep01", shots, montage.load_plan(ep, shots))
    assert "ep01/foley/f1" in problems


def test_envelope_reaches_edit_list(proj):
    ep = proj / "episodes" / "ep01"
    plan = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    plan["sfx"][0]["envelope"] = [[0, 0.2], [0.8, 1.0]]
    (ep / "audio.json").write_text(json.dumps(plan, ensure_ascii=False),
                                   encoding="utf-8")
    assert _build(proj)["sfx"][0]["envelope"] == [[0, 0.2], [0.8, 1.0]]


# --- баланс слоёв: подложка не должна глушить речь (правки 2026-09-05) ---

def test_ambience_gets_its_own_quiet_level(proj):
    """Непрерывная подложка и событийный эффект — разные слои.

    Живой прогон 2026-09-05: шестидесятисекундное море лежало в sfx с громкостью
    события и перекрывало речь. Подложка обязана быть заметно тише.
    """
    ep = proj / "episodes" / "ep01"
    plan = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    plan["sfx"][0]["ambience"] = True
    (ep / "audio.json").write_text(json.dumps(plan, ensure_ascii=False),
                                   encoding="utf-8")
    lst = _build(proj)
    assert lst["sfx"] == []
    assert lst["ambience"][0]["id"] == "s1"
    assert lst["ambience"][0]["volume"] == montage.AMBIENCE_VOLUME
    assert montage.AMBIENCE_VOLUME < montage.SFX_VOLUME


def test_event_sfx_stays_in_sfx(proj):
    lst = _build(proj)
    assert lst["sfx"][0]["id"] == "s1"
    assert lst["ambience"] == []


# --- режим кадров: эпизод без единого отрезка -----------------------------

def _stills_project(proj):
    """Тот же проект в режиме кадров: отрезки не снимались вовсе."""
    path = proj / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update({"genre": "educational", "visual_mode": "stills"})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    ep = proj / "episodes" / "ep01"
    (ep / "storyboard").mkdir(exist_ok=True)
    manifest = Manifest(proj / "manifest.json")
    for n in (1, 2, 3):
        (ep / "storyboard" / f"{n:03d}.png").write_bytes(b"stub")
        _accept(manifest, f"ep01/storyboard/{n:03d}", "frame")
    manifest.save()
    return load_project(path)


def test_stills_mode_lists_frames_instead_of_segments(proj):
    project = _stills_project(proj)
    shots = load_shots(proj / "episodes" / "ep01" / "shots.json", proj)
    manifest = Manifest(proj / "manifest.json")

    sheet = montage.build_edit_list(project, proj, "ep01", shots, manifest)

    assert sheet["mode"] == "stills"
    assert sheet["segments"] == []
    assert [s["n"] for s in sheet["stills"]] == [1, 2, 3]
    assert sheet["stills"][0]["file"].endswith("001.png")


def test_stills_carry_no_durations(proj):
    """Лист остаётся намерением: сколько висит кадр, измерит монтаж по репликам."""
    project = _stills_project(proj)
    shots = load_shots(proj / "episodes" / "ep01" / "shots.json", proj)
    sheet = montage.build_edit_list(project, proj, "ep01", shots,
                                    Manifest(proj / "manifest.json"))

    for still in sheet["stills"]:
        assert "duration" not in still
        assert "seconds" not in still
    assert "minSeconds" in sheet["stillsSettings"]


def test_stills_mode_does_not_demand_segment_files(proj):
    """Отрезков нет на диске — и это не ошибка: их не снимали."""
    project = _stills_project(proj)
    for n in (1, 2):
        (proj / "episodes" / "ep01" / "segments" / f"{n:03d}.mp4").unlink()

    shots = load_shots(proj / "episodes" / "ep01" / "shots.json", proj)
    sheet = montage.build_edit_list(project, proj, "ep01", shots,
                                    Manifest(proj / "manifest.json"))
    assert sheet["stills"]


def test_stills_mode_requires_accepted_frames(proj):
    """Кадр, не прошедший приёмку, в монтаж не попадает — как и отрезок."""
    project = _stills_project(proj)
    manifest = Manifest(proj / "manifest.json")
    manifest.data["items"]["ep01/storyboard/002"]["status"] = "generated"
    manifest.save()

    shots = load_shots(proj / "episodes" / "ep01" / "shots.json", proj)
    with pytest.raises(montage.MontageError) as e:
        montage.build_edit_list(project, proj, "ep01", shots,
                                Manifest(proj / "manifest.json"))
    assert "002" in str(e.value)


def test_video_mode_keeps_segments_and_has_no_stills(proj):
    project = load_project(proj / "project.json")
    shots = load_shots(proj / "episodes" / "ep01" / "shots.json", proj)
    sheet = montage.build_edit_list(project, proj, "ep01", shots,
                                    Manifest(proj / "manifest.json"))
    assert sheet["mode"] == "video"
    assert sheet["stills"] == []
    assert len(sheet["segments"]) == 2


# --- микшер в листе ---------------------------------------------------------

def _with_mix(pdir, mix):
    data = json.loads((pdir / "project.json").read_text("utf-8"))
    data["mix"] = mix
    (pdir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_track_volumes_come_from_the_mix_block(proj):
    _with_mix(proj, {"volumes": {"music": 0.3, "sfx": 0.2}})

    sheet = _build(proj)

    assert sheet["music"][0]["volume"] == 0.3
    assert sheet["sfx"][0]["volume"] == 0.2


def test_muted_track_stays_in_the_sheet_at_zero(proj):
    """Выключенная дорожка не выброшена: вернуть её — снять галку, а не
    пересобирать лист."""
    _with_mix(proj, {"muted": ["music"]})

    sheet = _build(proj)

    assert len(sheet["music"]) == 1
    assert sheet["music"][0]["volume"] == 0.0


def test_speaker_gain_multiplies_the_voice_volume(proj):
    """Множитель, а не замена: дорожка речи остаётся одной и выключается разом."""
    _with_mix(proj, {"volumes": {"voice": 0.8}, "speakers": {"Устинья": 0.5}})

    sheet = _build(proj)

    assert sheet["voice"][0]["volume"] == pytest.approx(0.4)


def test_speaker_not_named_in_the_mix_keeps_the_track_volume(proj):
    _with_mix(proj, {"speakers": {"Гвоздь": 0.25}})

    sheet = _build(proj)

    assert sheet["voice"][0]["volume"] == montage.VOICE_VOLUME


def test_duck_comes_from_the_mix_block(proj):
    _with_mix(proj, {"duck": {"gain": 0.5, "attack_ms": 200,
                              "release_ms": 900}})

    sheet = _build(proj)

    assert sheet["duck"] == {"gain": 0.5, "attackMs": 200.0, "releaseMs": 900.0}


def test_broken_mix_block_is_refused_before_the_sheet(proj):
    _with_mix(proj, {"volumes": {"music": "громко"}})

    with pytest.raises(montage.MontageError):
        _build(proj)


# --- субтитры и формат ------------------------------------------------------

# Тесты чдирят в tmp, поэтому карточки жанров передаются явным путём.
KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"



def _regenre(pdir, genre):
    data = json.loads((pdir / "project.json").read_text("utf-8"))
    data["genre"] = genre
    (pdir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_format_follows_the_aspect_of_the_project(proj):
    project, _shots, _m = _load(proj)
    assert montage.format_for(project) == "16x9"

    data = json.loads((proj / "project.json").read_text("utf-8"))
    data["format"] = "shorts_9x16"
    (proj / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    project, _shots, _m = _load(proj)
    assert montage.format_for(project) == "9x16"


def test_captions_default_to_shorts_only(proj):
    """Три жанра из четырёх объявляют `shorts_only` — прежнее поведение."""
    project, _shots, _m = _load(proj)

    assert montage.captions_on(project, "9x16", KNOWLEDGE) is True
    assert montage.captions_on(project, "16x9", KNOWLEDGE) is False


def test_educational_genre_gets_captions_in_any_format(proj):
    """`captions: always` объявлялся с 2026-09-07 и не читался никем."""
    _regenre(proj, "educational")
    project, _shots, _m = _load(proj)

    assert montage.captions_on(project, "16x9", KNOWLEDGE) is True


def test_unreadable_genre_keeps_the_old_behaviour(proj):
    """Молча включить или выключить субтитры хуже, чем остаться при дефолте."""
    _regenre(proj, "нет-такого-жанра")
    project = load_project(proj / "project.json")

    assert montage.captions_on(project, "9x16", KNOWLEDGE) is True
    assert montage.captions_on(project, "16x9", KNOWLEDGE) is False


def test_edit_list_carries_the_captions_flag(proj):
    assert _build(proj)["captions"] is False
    assert _build(proj, fmt="9x16")["captions"] is True


def test_educational_edit_list_asks_for_captions_in_16x9(proj):
    """Сквозная проверка: карточка жанра доезжает до листа, а не теряется."""
    _regenre(proj, "educational")

    assert _build(proj)["captions"] is True


# --- режим кадров: гейт приёмки смотрит на кадры ---------------------------

STILLS_SHOTS = {"episode": "ep01",
                "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}]}
STILLS_PLAN = {"voice_lines": [{"id": "v1", "segment": 1, "offset": 0.0,
                                "speaker": "Диктор", "voice": "Charon",
                                "text": "раз"}],
               "music_cues": [], "sfx": [], "foley": []}


def test_review_gate_survives_an_episode_without_segments():
    """Раньше здесь был `shots["segments"]` — в режиме кадров это KeyError,
    то есть трейсбек вместо гейта (дымовой прогон 2026-09-08)."""
    manifest = Manifest(Path("нет-такого") / "manifest.json")

    problems = montage.review_problems(manifest, "ep01", STILLS_SHOTS,
                                       STILLS_PLAN)

    assert problems["ep01/storyboard/001"] == "не генерировался"
    assert problems["ep01/storyboard/002"] == "не генерировался"


def test_review_gate_passes_when_frames_are_accepted(tmp_path):
    manifest = Manifest(tmp_path / "manifest.json")
    for n in (1, 2):
        _accept(manifest, f"ep01/storyboard/{n:03d}", "frame")
    _accept(manifest, "ep01/audio/v1", "voice")

    assert montage.review_problems(manifest, "ep01", STILLS_SHOTS,
                                   STILLS_PLAN) == {}
