import json
import pytest
from factory.project import load_project, ProjectError


def write(tmp_path, data):
    p = tmp_path / "project.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


BASE = {
    "name": "pilot", "type": "animated_series", "theme": "space cats",
    "audience": "6-9", "episodes": 1, "episode_duration_sec": 75,
    "models": {"image": "nano-banana-2", "video": "kling-2.0"},
}


def test_loads_valid_animated_series(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.type == "animated_series"
    assert p.segment_seconds == 5            # high quality — дефолт
    assert p.review_strictness == "medium"   # дефолт


def test_budget_mode_gives_10s_segments(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "quality_mode": "budget"}))
    assert p.segment_seconds == 10


def test_missing_required_field_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "audience"}
    with pytest.raises(ProjectError, match="audience"):
        load_project(write(tmp_path, data))


def test_unknown_type_raises(tmp_path):
    with pytest.raises(ProjectError, match="unknown project type"):
        load_project(write(tmp_path, {**BASE, "type": "opera"}))


def test_missing_video_model_raises(tmp_path):
    with pytest.raises(ProjectError, match="models.video"):
        load_project(write(tmp_path, {**BASE, "models": {"image": "nano-banana-2"}}))


def test_missing_name_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "name"}
    with pytest.raises(ProjectError, match="name"):
        load_project(write(tmp_path, data))


def test_missing_models_entirely_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "models"}
    with pytest.raises(ProjectError, match="models is required"):
        load_project(write(tmp_path, data))


def test_unknown_strictness_raises(tmp_path):
    with pytest.raises(ProjectError, match="unknown review_strictness"):
        load_project(write(tmp_path, {**BASE, "review_strictness": "paranoid"}))
