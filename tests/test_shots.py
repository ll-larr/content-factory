import json
from pathlib import Path

import pytest
from factory.shots import load_shots, ShotsError


# --- единая конвенция путей файлов (закрытие TODO mix_audio.py) ---

def test_segment_path_convention():
    from factory.shots import segment_path
    assert segment_path(Path("projects/p/episodes/ep01"), 3) == \
        Path("projects/p/episodes/ep01/segments/003.mp4")


def test_frame_path_convention():
    from factory.shots import frame_path
    assert frame_path(Path("projects/p/episodes/ep01"), 7) == \
        Path("projects/p/episodes/ep01/storyboard/007.png")


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


def test_same_start_end_frame_allowed(tmp_path):
    # статичный план: start == end — валидно, интерпретация на стороне видеомодели
    good = json.loads(json.dumps(GOOD))
    good["segments"][1] = {"n": 2, "start_frame": 2, "end_frame": 2, "prompt": "x"}
    good["frames"][1].pop("refs")
    data = load_shots(write(tmp_path, good), tmp_path)
    assert len(data["segments"]) == 2


def test_missing_ref_raises(tmp_path):
    with pytest.raises(ShotsError, match="missing ref"):
        load_shots(write(tmp_path, GOOD), tmp_path)  # png не создан


def test_all_missing_refs_are_listed_at_once(tmp_path):
    """D-5: отсутствующие референсы собираются в один список, а не роняют загрузку
    на первом же. На серии из тринадцати кадров чинить по одному — против
    устоявшегося в репо поведения: остальные гейты показывают список разом."""
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][0]["refs"] = ["bible/characters/a-ref.png"]
    bad["frames"][2]["refs"] = ["bible/characters/c-ref.png"]
    with pytest.raises(ShotsError) as excinfo:
        load_shots(write(tmp_path, bad), tmp_path)
    message = str(excinfo.value)
    for name in ("a-ref.png", "kepler-ref.png", "c-ref.png"):
        assert name in message, message


def test_absent_file_raises_shots_error(tmp_path):
    """Загрузчик отвечает своей ошибкой и на «файла нет»: иначе вызывающий код
    ловит ShotsError, а получает голый OSError (тот же трейсбек, что в D-4)."""
    with pytest.raises(ShotsError):
        load_shots(tmp_path / "нет-такого.json", tmp_path)


def test_broken_json_raises_shots_error(tmp_path):
    p = tmp_path / "shots.json"
    p.write_text("{не json", encoding="utf-8")
    with pytest.raises(ShotsError):
        load_shots(p, tmp_path)


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
    del bad["segments"][0]["start_frame"]
    bad["frames"][1].pop("refs")  # убираем ref, чтобы не сработала проверка missing ref раньше целевой
    with pytest.raises(ShotsError, match="missing required key"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_without_end_frame_allowed(tmp_path):
    # Отрезок без end_frame — движение ВНУТРИ одного плана: модель получает только
    # первый кадр и никуда не интерполирует. Пара кадров разных планов заставляла её
    # перетекать из локации в локацию (живой прогон 2026-09-03: «дом строится из
    # ниоткуда»), поэтому склейка планов — работа монтажа, а не видеомодели.
    good = json.loads(json.dumps(GOOD))
    del good["segments"][0]["end_frame"]
    good["frames"][1].pop("refs")
    data = load_shots(write(tmp_path, good), tmp_path)
    assert "end_frame" not in data["segments"][0]


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


# --- refs не должны выходить за пределы проекта (ревью безопасности 2026-09-05) ---

def test_ref_outside_project_rejected(tmp_path):
    """Существование файла — не признак того, что его можно читать.

    refs уезжают провайдеру: _media читает файл и base64-кодирует его в тело
    запроса. Ссылка вида ../../secrets проходила проверку существования и
    отправляла чужой файл наружу.
    """
    (tmp_path / "bible" / "characters").mkdir(parents=True)
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("s3cret", encoding="utf-8")
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][1]["refs"] = ["../secret.txt"]
    with pytest.raises(ShotsError, match="вне проекта|outside"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_absolute_ref_rejected(tmp_path):
    # project_dir / "C:/..." молча отбрасывает project_dir
    (tmp_path / "bible" / "characters").mkdir(parents=True)
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][1]["refs"] = [str(tmp_path.parent / "any.png")]
    with pytest.raises(ShotsError, match="вне проекта|outside|абсолют"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_ref_inside_project_still_ok(tmp_path):
    (tmp_path / "bible" / "characters").mkdir(parents=True)
    (tmp_path / "bible" / "characters" / "kepler-ref.png").write_bytes(b"x")
    data = load_shots(write(tmp_path, GOOD), tmp_path)
    assert data["frames"][1]["refs"] == ["bible/characters/kepler-ref.png"]
