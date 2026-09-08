"""Тесты scripts/render.py — команды монтажа (спека 2026-08-31 §8).

Node здесь не запускается: проверяется поведение Python-стороны — гейты, коды
возврата и та команда, которую она собирается выполнить.
"""
import json

from pathlib import Path

import pytest

import render
from factory.manifest import Manifest
from test_montage import AUDIO, PROJECT, SHOTS, _accept  # noqa: F401


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


@pytest.fixture
def spy(monkeypatch):
    """Подменяет запуск Node: тест смотрит на команду, а не рендерит."""
    calls = []

    def fake(cmd, **kwargs):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(render, "run_node", fake)
    return calls


def run(proj, *extra):
    return render.main(["--project", str(proj), "--episode", "ep01", *extra])


def test_dry_run_prints_edit_list_and_touches_no_node(proj, spy, capsys):
    assert run(proj, "--dry-run") == 0
    assert spy == []
    printed = json.loads(capsys.readouterr().out)
    assert printed["episode"] == "ep01"
    assert len(printed["segments"]) == 2


def test_unreviewed_segment_blocks_with_code_3(proj, spy, capsys):
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/segments/002", "pending")
    m.save()
    assert run(proj) == 3
    assert spy == []
    assert "ep01/segments/002" in capsys.readouterr().out


def test_unreviewed_audio_blocks_too(proj, spy, capsys):
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/audio/v1", "pending")
    m.save()
    assert run(proj) == 3
    assert "ep01/audio/v1" in capsys.readouterr().out


def test_missing_file_is_data_error_code_1(proj, spy, capsys):
    (proj / "episodes/ep01/segments/001.mp4").unlink()
    assert run(proj) == 1
    assert spy == []
    assert "001.mp4" in capsys.readouterr().out


def test_render_invokes_composition_with_props_and_public_dir(proj, spy):
    assert run(proj) == 0
    cmd = " ".join(spy[0])
    assert "Episode16x9" in cmd
    assert "--props=" in cmd
    assert "--public-dir=" in cmd
    assert str(proj / "episodes" / "ep01" / "final" / "ep01.mp4") in cmd


def test_shorts_format_picks_other_composition_and_filename(proj, spy):
    assert run(proj, "--format", "9x16") == 0
    cmd = " ".join(spy[0])
    assert "Episode9x16" in cmd
    assert "ep01-9x16.mp4" in cmd


def test_audio_only_renders_mix_next_to_episode(proj, spy):
    assert run(proj, "--audio-only") == 0
    cmd = " ".join(spy[0])
    assert "--codec=aac" in cmd
    assert str(proj / "episodes" / "ep01" / "audio" / "mix.m4a") in cmd


def test_studio_starts_studio_and_renders_nothing(proj, spy):
    assert run(proj, "--studio") == 0
    cmd = " ".join(spy[0])
    assert "studio" in cmd
    assert "--props=" in cmd
    assert ".mp4" not in cmd


def test_node_failure_is_reported_as_code_1(proj, monkeypatch, capsys):
    monkeypatch.setattr(render, "run_node", lambda cmd, **kw: 7)
    assert run(proj) == 1
    assert "рендер" in capsys.readouterr().out.lower()


# --- мастеринг громкости (дизайн 2026-09-04 §6.1) ---

def test_master_skips_when_correction_is_inaudible(monkeypatch, capsys, tmp_path):
    import render
    monkeypatch.setattr(render, "measure_loudness", lambda p: -14.2)
    called = []
    monkeypatch.setattr(render, "apply_gain",
                        lambda *a: called.append(a))
    assert render._master(tmp_path / "ep01.mp4", -14.0) == 0
    assert called == []
    assert "не нужна" in capsys.readouterr().out


def test_master_applies_gain_and_replaces_file(monkeypatch, capsys, tmp_path):
    import render
    dest = tmp_path / "ep01.mp4"
    dest.write_bytes(b"original")
    monkeypatch.setattr(render, "measure_loudness", lambda p: -23.0)

    def fake_gain(src, out, gain_db):
        Path(out).write_bytes(b"mastered")
        return out

    monkeypatch.setattr(render, "apply_gain", fake_gain)
    assert render._master(dest, -14.0) == 0
    assert dest.read_bytes() == b"mastered"
    assert "-23.0 -> -14.0" in capsys.readouterr().out


def test_master_failure_keeps_rendered_file(monkeypatch, capsys, tmp_path):
    # Неудача мастеринга не отменяет уже отрендеренный эпизод: файл на месте,
    # ему просто не поправили уровень.
    import render
    from factory.ffmpeg_tools import FfmpegError
    dest = tmp_path / "ep01.mp4"
    dest.write_bytes(b"original")
    monkeypatch.setattr(render, "measure_loudness", lambda p: -30.0)

    def boom(src, out, gain_db):
        raise FfmpegError("ffmpeg упал")

    monkeypatch.setattr(render, "apply_gain", boom)
    assert render._master(dest, -14.0) == 0
    assert dest.read_bytes() == b"original"
    assert "ВНИМАНИЕ" in capsys.readouterr().out


def test_render_calls_master_with_project_target(proj, monkeypatch):
    # target_lufs берётся из project.json, а не из константы кода.
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["target_lufs"] = -16.0
    (proj / "project.json").write_text(json.dumps(pj, ensure_ascii=False),
                                       encoding="utf-8")
    monkeypatch.setattr(render, "run_node", lambda cmd, **kw: 0)
    seen = {}
    monkeypatch.setattr(render, "_master",
                        lambda dest, target: seen.update(dest=dest, target=target) or 0)
    assert render.main(["--project", str(proj), "--episode", "ep01"]) == 0
    assert seen["target"] == -16.0
    assert str(seen["dest"]).endswith("ep01.mp4")


def test_render_master_disabled_by_null(proj, monkeypatch):
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["target_lufs"] = None
    (proj / "project.json").write_text(json.dumps(pj, ensure_ascii=False),
                                       encoding="utf-8")
    monkeypatch.setattr(render, "run_node", lambda cmd, **kw: 0)
    called = []
    monkeypatch.setattr(render, "_master", lambda *a: called.append(a) or 0)
    assert render.main(["--project", str(proj), "--episode", "ep01"]) == 0
    assert called == []


def test_render_audio_only_is_not_mastered(proj, monkeypatch):
    # Предпрослушка — рабочий инструмент, а не то, что уходит зрителю.
    monkeypatch.setattr(render, "run_node", lambda cmd, **kw: 0)
    called = []
    monkeypatch.setattr(render, "_master", lambda *a: called.append(a) or 0)
    assert render.main(["--project", str(proj), "--episode", "ep01",
                        "--audio-only"]) == 0
    assert called == []


# --- формат берётся из проекта ---------------------------------------------

def _retype(pdir, **changes):
    data = json.loads((pdir / "project.json").read_text("utf-8"))
    data.update(changes)
    (pdir / "project.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_vertical_project_renders_vertical_without_a_flag(proj, spy):
    """Шортс, собранный из панели, выходил горизонтальным: флаг `--format` имел
    дефолт «16x9», а панель его не передавала."""
    _retype(proj, format="shorts_9x16")

    assert run(proj) == 0
    assert "Episode9x16" in spy[0]


def test_horizontal_project_still_renders_horizontal(proj, spy):
    assert run(proj) == 0
    assert "Episode16x9" in spy[0]


def test_explicit_flag_overrides_the_project(proj, spy):
    """Вертикальная нарезка горизонтального проекта — осознанное действие."""
    assert run(proj, "--format", "9x16") == 0
    assert "Episode9x16" in spy[0]


def test_vertical_project_names_the_file_by_the_format(proj, spy):
    """Имя файла тоже идёт от формата проекта, а не от флага, которого нет."""
    _retype(proj, format="shorts_9x16")
    run(proj)

    assert any("ep01-9x16.mp4" in str(arg) for arg in spy[0])
