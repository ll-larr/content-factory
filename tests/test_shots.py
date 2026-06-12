import json
import pytest
from factory.shots import load_shots, ShotsError


def write(tmp_path, data):
    p = tmp_path / "shots.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


GOOD = {
    "episode": "ep01",
    "frames": [
        {"n": 1, "prompt": "cat in corridor"},
        {"n": 2, "prompt": "cat at panel", "refs": ["bible/characters/kepler-ref.png"]},
        {"n": 3, "prompt": "cat presses button"},
    ],
    "segments": [
        {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "cat walks"},
        {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "cat reaches"},
    ],
}


def test_valid_plan_loads(tmp_path):
    (tmp_path / "bible" / "characters").mkdir(parents=True)
    (tmp_path / "bible" / "characters" / "kepler-ref.png").write_bytes(b"x")
    data = load_shots(write(tmp_path, GOOD), tmp_path)
    assert len(data["frames"]) == 3


def test_unchained_segments_allowed(tmp_path):
    # переходы между сценами: отрезок 2 начинается не с конца отрезка 1 — это валидно
    good = json.loads(json.dumps(GOOD))
    good["segments"][1] = {"n": 2, "start_frame": 1, "end_frame": 3, "prompt": "x"}
    good["frames"][1].pop("refs")
    data = load_shots(write(tmp_path, good), tmp_path)
    assert len(data["segments"]) == 2


def test_missing_ref_raises(tmp_path):
    with pytest.raises(ShotsError, match="missing ref"):
        load_shots(write(tmp_path, GOOD), tmp_path)  # png не создан


def test_frame_gap_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][2]["n"] = 5
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="without gaps"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_fewer_segments_than_frames_allowed(tmp_path):
    # 3 кадра, 1 отрезок — теперь валидно (переходы не обязаны покрывать все кадры)
    good = json.loads(json.dumps(GOOD))
    good["segments"] = [good["segments"][0]]
    good["frames"][1].pop("refs")
    data = load_shots(write(tmp_path, good), tmp_path)
    assert len(data["segments"]) == 1


def test_frame_missing_n_key_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    del bad["frames"][2]["n"]
    bad["frames"][1].pop("refs")  # убираем ref, чтобы не сработала проверка missing ref раньше целевой
    with pytest.raises(ShotsError, match="missing required key"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_missing_key_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    del bad["segments"][0]["end_frame"]
    bad["frames"][1].pop("refs")  # убираем ref, чтобы не сработала проверка missing ref раньше целевой
    with pytest.raises(ShotsError, match="missing required key"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_empty_segments_with_multi_frame_allowed(tmp_path):
    # пустой список отрезков с несколькими кадрами теперь валиден
    good = json.loads(json.dumps(GOOD))
    good["segments"] = []
    good["frames"][1].pop("refs")
    data = load_shots(write(tmp_path, good), tmp_path)
    assert data["segments"] == []


def test_segment_start_frame_missing_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"][0] = {"n": 1, "start_frame": 99, "end_frame": 2, "prompt": "x"}
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="segment 1: start_frame 99 references missing frame"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_end_frame_missing_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"][1] = {"n": 2, "start_frame": 2, "end_frame": 99, "prompt": "x"}
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="segment 2: end_frame 99 references missing frame"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_gap_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"][1]["n"] = 3  # пропуск: 1, 3 — без 2
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="without gaps"):
        load_shots(write(tmp_path, bad), tmp_path)
