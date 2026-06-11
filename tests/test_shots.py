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


def test_broken_chain_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"][1] = {"n": 2, "start_frame": 1, "end_frame": 3, "prompt": "x"}
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="must chain frames"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_missing_ref_raises(tmp_path):
    with pytest.raises(ShotsError, match="missing ref"):
        load_shots(write(tmp_path, GOOD), tmp_path)  # png не создан


def test_frame_gap_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][2]["n"] = 5
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="without gaps"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_count_mismatch_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"] = bad["segments"][:1]
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="require 2 segments"):
        load_shots(write(tmp_path, bad), tmp_path)


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


def test_empty_segments_with_multi_frame_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"] = []
    bad["frames"][1].pop("refs")  # убираем ref, чтобы не сработала проверка missing ref раньше целевой
    with pytest.raises(ShotsError, match="require 2 segments"):
        load_shots(write(tmp_path, bad), tmp_path)
