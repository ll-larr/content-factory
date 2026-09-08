"""Тесты audio_plan.py (спека фазы 2 §4)."""
import json
from pathlib import Path

import pytest

from factory.audio_plan import AudioPlanError, is_empty, load_audio_plan

SHOTS = {"episode": "ep01",
         "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}],
         "segments": [{"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m"}]}

VALID = {
    "voice_lines": [{"id": "vl-01", "speaker": "cat", "voice": "Ashley",
                     "text": "Hi!", "segment": 1, "offset": 0.5}],
    "music_cues": [{"id": "mus-01", "prompt": "calm", "duration": 10,
                    "segment": 1, "offset": 0}],
    "sfx": [{"id": "sfx-01", "prompt": "creak", "duration": 3,
             "segment": 1, "offset": 1.0}],
}


def write_plan(tmp_path, data):
    p = tmp_path / "audio.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_valid_plan_loads(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, VALID), SHOTS)
    assert plan["voice_lines"][0]["id"] == "vl-01"
    assert plan["voice_lines"][0]["offset"] == 0.5
    assert not is_empty(plan)


def test_missing_lists_default_to_empty(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, {}), SHOTS)
    assert plan["voice_lines"] == []
    assert plan["music_cues"] == []
    assert plan["sfx"] == []
    assert is_empty(plan)


def test_duplicate_id_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["id"] = "vl-01"
    with pytest.raises(AudioPlanError, match="duplicate id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_missing_voice_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    del data["voice_lines"][0]["voice"]
    with pytest.raises(AudioPlanError, match="voice"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_missing_text_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["text"] = ""
    with pytest.raises(AudioPlanError, match="text"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_bad_duration_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["music_cues"][0]["duration"] = 0
    with pytest.raises(AudioPlanError, match="duration"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_unknown_segment_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["segment"] = 99
    with pytest.raises(AudioPlanError, match="segment 99"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_negative_offset_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["offset"] = -1
    with pytest.raises(AudioPlanError, match="offset"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_entry_without_id_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    del data["sfx"][0]["id"]
    with pytest.raises(AudioPlanError, match="without id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_missing_segment_field_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    del data["voice_lines"][0]["segment"]
    with pytest.raises(AudioPlanError, match="missing 'segment'"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


# --- дуга подачи, огибающая громкости, липсинк и фоли (дизайн 2026-09-04) ---

def test_direction_and_lipsync_are_optional(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, VALID), SHOTS)
    assert plan["voice_lines"][0].get("direction") is None
    assert plan["voice_lines"][0]["lipsync"] is False


def test_direction_and_lipsync_kept(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["direction"] = "flat, decision already made"
    data["voice_lines"][0]["lipsync"] = True
    plan = load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert plan["voice_lines"][0]["direction"] == "flat, decision already made"
    assert plan["voice_lines"][0]["lipsync"] is True


def test_envelope_accepted_on_every_list(tmp_path):
    data = json.loads(json.dumps(VALID))
    for name in ("voice_lines", "music_cues", "sfx"):
        data[name][0]["envelope"] = [[0, 0.0], [1.5, 1.0], [3, 0.2]]
    plan = load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert plan["sfx"][0]["envelope"][1] == [1.5, 1.0]


def test_envelope_must_be_pairs(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["envelope"] = [[0, 1.0], [2]]
    with pytest.raises(AudioPlanError, match="envelope"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_envelope_time_must_not_go_backwards(tmp_path):
    # Точки читаются по порядку: непорядок почти всегда опечатка, а молча
    # отсортировать значило бы тихо поменять авторский замысел громкости.
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["envelope"] = [[0, 1.0], [3, 0.5], [2, 0.0]]
    with pytest.raises(AudioPlanError, match="envelope"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_envelope_level_must_be_in_range(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["envelope"] = [[0, 1.0], [1, 5.0]]
    with pytest.raises(AudioPlanError, match="envelope"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_foley_needs_segment_and_prompt(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["foley"] = [{"id": "fol-01", "segment": 1, "prompt": "boots on wet iron"}]
    plan = load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert plan["foley"][0]["prompt"] == "boots on wet iron"
    # длительность фоли задаёт сам отрезок, поэтому её в плане нет
    assert "duration" not in plan["foley"][0]


def test_foley_missing_prompt_raises(tmp_path):
    # mmaudio-v2 требует prompt по схеме — без него отказ до траты, а не HTTP 400
    data = json.loads(json.dumps(VALID))
    data["foley"] = [{"id": "fol-01", "segment": 1}]
    with pytest.raises(AudioPlanError, match="prompt"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_foley_one_per_segment(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["foley"] = [{"id": "fol-01", "segment": 1, "prompt": "a"},
                     {"id": "fol-02", "segment": 1, "prompt": "b"}]
    with pytest.raises(AudioPlanError, match="foley"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_process_field_validated_against_known_names(tmp_path):
    # Опечатка в имени обработки должна ловиться планом, а не всплывать после
    # оплаченной генерации на попытке применить фильтр.
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["process"] = "tinn"
    with pytest.raises(AudioPlanError, match="process"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_known_process_kept(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["process"] = "tin"
    plan = load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert plan["voice_lines"][0]["process"] == "tin"


def test_process_defaults_to_none(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, VALID), SHOTS)
    assert plan["voice_lines"][0].get("process") is None


# --- id как имя файла (находка ревью безопасности 2026-09-05) ---

def test_id_with_traversal_rejected(tmp_path):
    """`id` становится путём файла — значит обязан быть ОДНИМ компонентом пути.

    Без проверки запись уходила за пределы проекта: audio_unit_path склеивает
    id напрямую, а download создаёт каталоги и подменяет файл. Тот же класс
    ошибки, ради которого в preprod уже живёт is_safe_name.
    """
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["id"] = "../../../../pwned"
    with pytest.raises(AudioPlanError, match="id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_absolute_id_rejected(tmp_path):
    # Path("a/b") / "C:/tmp/x" отбрасывает левую часть целиком — абсолютный id
    # опаснее относительного.
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["id"] = "C:/tmp/pwned"
    with pytest.raises(AudioPlanError, match="id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_backslash_id_rejected(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["music_cues"][0]["id"] = "..\..\pwned"
    with pytest.raises(AudioPlanError, match="id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_ordinary_id_still_accepted(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, VALID), SHOTS)
    assert plan["voice_lines"][0]["id"] == "vl-01"


def test_two_lipsync_lines_on_one_segment_rejected(tmp_path):
    """Липсинк адресуется ОТРЕЗКОМ, а не идентификатором реплики.

    Ревью 2026-09-05: два задания получали одинаковые item_id и dest; первое
    платило и писало файл, второе падало необработанным ManifestError уже после
    траты. Та же причина, по которой одна дорожка фоли на отрезок.
    """
    data = json.loads(json.dumps(VALID))
    data["voice_lines"] = [
        {"id": "vl-01", "speaker": "a", "voice": "Kore", "text": "раз",
         "segment": 1, "offset": 0.0, "lipsync": True},
        {"id": "vl-02", "speaker": "b", "voice": "Kore", "text": "два",
         "segment": 1, "offset": 1.4, "lipsync": True},
    ]
    with pytest.raises(AudioPlanError, match="lipsync"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_two_lines_on_one_segment_without_lipsync_are_fine(tmp_path):
    # Без липсинка коллизии нет: у реплик свои файлы по своим id.
    data = json.loads(json.dumps(VALID))
    data["voice_lines"] = [
        {"id": "vl-01", "speaker": "a", "voice": "Kore", "text": "раз",
         "segment": 1, "offset": 0.0},
        {"id": "vl-02", "speaker": "b", "voice": "Kore", "text": "два",
         "segment": 1, "offset": 1.4},
    ]
    plan = load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert len(plan["voice_lines"]) == 2


def test_id_error_message_names_the_backslash(tmp_path):
    # Сообщение перечисляет запрещённые разделители; сломанное экранирование
    # съедало обратный слэш и оставляло пустые кавычки.
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["id"] = "../x"
    with pytest.raises(AudioPlanError) as e:
        load_audio_plan(write_plan(tmp_path, data), SHOTS)
    assert "\\" in str(e.value)


# --- режим кадров: единица плана — кадр, а не отрезок ----------------------

STILLS_SHOTS = {"episode": "ep01",
                "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                           {"n": 3, "prompt": "c"}]}


def test_plan_binds_to_frames_when_there_are_no_segments(tmp_path):
    """Режим `stills` не собирался вовсе: валидатор сверял номера только с
    отрезками, которых там нет, и отбивал ЛЮБУЮ реплику (дымовой прогон
    2026-09-08)."""
    plan = load_audio_plan(write_plan(tmp_path, {
        "voice_lines": [{"id": "v3", "speaker": "Диктор", "voice": "Charon",
                         "text": "Третий кадр.", "segment": 3, "offset": 0.0}],
        "music_cues": [], "sfx": [],
    }), STILLS_SHOTS)

    assert plan["voice_lines"][0]["segment"] == 3


def test_frame_number_out_of_range_is_still_refused(tmp_path):
    with pytest.raises(AudioPlanError) as e:
        load_audio_plan(write_plan(tmp_path, {
            "voice_lines": [{"id": "v9", "speaker": "Диктор", "voice": "Charon",
                             "text": "Нет такого кадра.", "segment": 9,
                             "offset": 0.0}],
            "music_cues": [], "sfx": [],
        }), STILLS_SHOTS)
    # Сообщение называет, с чем сверяли: «missing segment» в режиме кадров
    # отправляло чинить то, чего в этом эпизоде нет по замыслу.
    assert "frame" in str(e.value)


def test_segments_win_when_both_exist(tmp_path):
    """У обычного эпизода координаты — отрезки, и кадр номер 2 не оправдание."""
    shots = {"episode": "ep01",
             "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}],
             "segments": [{"n": 1, "start_frame": 1, "prompt": "m"}]}

    with pytest.raises(AudioPlanError):
        load_audio_plan(write_plan(tmp_path, {
            "voice_lines": [{"id": "v2", "speaker": "cat", "voice": "Ashley",
                             "text": "Hi!", "segment": 2, "offset": 0.0}],
            "music_cues": [], "sfx": [],
        }), shots)
