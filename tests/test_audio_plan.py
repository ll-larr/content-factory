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
