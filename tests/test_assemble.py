"""Тесты assemble.py (спека фазы 2 §8): гейт отрезков, склейка, контроль ±5%."""
import json
from pathlib import Path

import pytest

import assemble
from factory.ffmpeg_tools import has_audio_stream, probe_duration
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path, monkeypatch, make_clip):
    """Проект: 2 отрезка по 5с (quality high), реальные крошечные mp4, оба done."""
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": "nano_banana_flash", "video": "kling3_0"},
    }), encoding="utf-8")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                   {"n": 3, "prompt": "c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    for n in (1, 2):
        make_clip(ep / "segments" / f"{n:03d}.mp4", 5.0)
    set_segment_statuses(pdir, "done")
    monkeypatch.chdir(tmp_path)
    return pdir


def set_segment_statuses(pdir, final_status):
    """Перезаписать манифест: оба отрезка проведены до final_status легальным путём."""
    m = Manifest(pdir / "manifest.json")
    m.data = {"items": {}}
    for n in (1, 2):
        item_id = f"ep01/segments/{n:03d}"
        m.add(item_id, kind="segment")
        m.set_status(item_id, "generating")
        m.set_status(item_id, "generated")
        if final_status == "rejected":
            m.set_status(item_id, "rejected", reject_reason="r")
        elif final_status != "generated":
            m.set_status(item_id, final_status)
    m.save()


def run(proj):
    return assemble.main(["--project", str(proj), "--episode", "ep01"])


def test_happy_path(proj, capsys):
    assert run(proj) == 0
    dest = proj / "episodes" / "ep01" / "final" / "ep01.mp4"
    assert dest.exists()
    assert abs(probe_duration(dest) - 10.0) < 0.5
    out = capsys.readouterr().out
    assert "ВНИМАНИЕ" not in out          # длительность в допуске
    assert not has_audio_stream(dest)     # Task 1: звука ещё нет


def test_atomic_no_tmp_left(proj):
    assert run(proj) == 0
    final_dir = proj / "episodes" / "ep01" / "final"
    assert list(final_dir.glob("*.tmp.*")) == []


def test_gate_blocks_unreviewed(proj, capsys):
    set_segment_statuses(proj, "generated")
    assert run(proj) == 3
    out = capsys.readouterr().out
    assert "заблокирована" in out
    assert "ep01/segments/001" in out
    assert not (proj / "episodes" / "ep01" / "final" / "ep01.mp4").exists()


def test_gate_blocks_rejected(proj, capsys):
    set_segment_statuses(proj, "rejected")
    assert run(proj) == 3
    assert "статус rejected" in capsys.readouterr().out


def test_gate_blocks_never_generated(proj, capsys):
    (proj / "manifest.json").unlink()
    assert run(proj) == 3
    assert "не генерировался" in capsys.readouterr().out


def test_accepted_with_notes_passes_gate(proj):
    set_segment_statuses(proj, "accepted_with_notes")
    assert run(proj) == 0


def test_missing_segment_file(proj, capsys):
    (proj / "episodes" / "ep01" / "segments" / "002.mp4").unlink()
    assert run(proj) == 1
    assert "не найден" in capsys.readouterr().out


def test_duration_warning(proj, make_clip, capsys):
    # Реальные клипы по 1с при плане 2×5с → вне допуска ±5%
    for n in (1, 2):
        make_clip(proj / "episodes" / "ep01" / "segments" / f"{n:03d}.mp4", 1.0)
    assert run(proj) == 0  # файл сохраняется, exit 0
    out = capsys.readouterr().out
    assert "ВНИМАНИЕ" in out
    assert (proj / "episodes" / "ep01" / "final" / "ep01.mp4").exists()


def test_no_segments_in_shots(proj, capsys):
    ep = proj / "episodes" / "ep01"
    shots = json.loads((ep / "shots.json").read_text(encoding="utf-8"))
    shots["segments"] = []
    (ep / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    assert run(proj) == 1
    assert "собирать нечего" in capsys.readouterr().out
