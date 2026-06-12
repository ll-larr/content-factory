"""Тесты mix_audio.py (спека фазы 2 §7): гейт, таймлайн, ducking, пустой план."""
import json
from pathlib import Path

import pytest

import mix_audio
from factory.ffmpeg_tools import probe_duration
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path, monkeypatch, make_clip, make_tone):
    """Проект: 2 отрезка по 2с (реальные mp4), 1 реплика + 1 музыка + 1 SFX
    (реальные aac), все аудио-items в done."""
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
        make_clip(ep / "segments" / f"{n:03d}.mp4", 2.0)
    (ep / "audio.json").write_text(json.dumps({
        "voice_lines": [{"id": "vl-01", "speaker": "cat", "voice": "A",
                         "text": "Hi!", "segment": 1, "offset": 0.2}],
        "music_cues": [{"id": "mus-01", "prompt": "calm", "duration": 3,
                        "segment": 1, "offset": 0}],
        "sfx": [{"id": "sfx-01", "prompt": "creak", "duration": 1,
                 "segment": 2, "offset": 0.5}],
    }), encoding="utf-8")
    files = {
        "vl-01": make_tone(ep / "audio" / "voice" / "vl-01.m4a", 0.5),
        "mus-01": make_tone(ep / "audio" / "music" / "mus-01.m4a", 3.0),
        "sfx-01": make_tone(ep / "audio" / "sfx" / "sfx-01.m4a", 1.0),
    }
    m = Manifest(pdir / "manifest.json")
    kinds = {"vl-01": "voice", "mus-01": "music", "sfx-01": "sfx"}
    for eid, f in files.items():
        item_id = f"ep01/audio/{eid}"
        m.add(item_id, kind=kinds[eid])
        m.set_status(item_id, "generating")
        m.set_status(item_id, "generated", file=str(f))
        m.set_status(item_id, "done")
    m.save()
    monkeypatch.chdir(tmp_path)
    return pdir


def run(proj):
    return mix_audio.main(["--project", str(proj), "--episode", "ep01"])


def mix_path(proj):
    return proj / "episodes" / "ep01" / "audio" / "mix.m4a"


def test_happy_path(proj, capsys):
    assert run(proj) == 0
    assert mix_path(proj).exists()
    # Общая длительность = сумме отрезков (4с): atrim+apad
    assert abs(probe_duration(mix_path(proj)) - 4.0) < 0.3
    assert "Сведено" in capsys.readouterr().out


# done терминален — перевести готовый item обратно нельзя, поэтому гейт-тест
# строит манифест с нуля и доводит item только до generated:
def test_gate_blocks_unreviewed(proj, capsys):
    m = Manifest(proj / "manifest.json")
    f = m.get("ep01/audio/vl-01")["file"]
    m.data = {"items": {}}
    m.add("ep01/audio/vl-01", kind="voice")
    m.set_status("ep01/audio/vl-01", "generating")
    m.set_status("ep01/audio/vl-01", "generated", file=f)
    m.save()
    assert run(proj) == 3
    out = capsys.readouterr().out
    assert "заблокировано" in out
    assert "ep01/audio/vl-01" in out
    assert not mix_path(proj).exists()


def test_gate_blocks_never_generated(proj, capsys):
    (proj / "manifest.json").unlink()
    assert run(proj) == 3
    assert "не генерировался" in capsys.readouterr().out


def test_missing_audio_json_is_ok(proj, capsys):
    (proj / "episodes" / "ep01" / "audio.json").unlink()
    assert run(proj) == 0
    assert not mix_path(proj).exists()
    assert "без звука" in capsys.readouterr().out


def test_empty_plan_is_ok(proj, capsys):
    (proj / "episodes" / "ep01" / "audio.json").write_text(
        json.dumps({"voice_lines": [], "music_cues": [], "sfx": []}),
        encoding="utf-8")
    assert run(proj) == 0
    assert not mix_path(proj).exists()
    assert "пуст" in capsys.readouterr().out


def test_overflow_warning(proj, capsys):
    # Реплика 0.5с на offset 1.8 при отрезке 2с → вылезает за границу
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"][0]["offset"] = 1.8
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert "вылезает" in capsys.readouterr().out


def test_voice_only_no_music(proj):
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["music_cues"] = []
    data["sfx"] = []
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert mix_path(proj).exists()


def test_music_only_no_speech(proj):
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"] = []
    data["sfx"] = []
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert mix_path(proj).exists()


def test_missing_audio_file(proj, capsys):
    (proj / "episodes" / "ep01" / "audio" / "voice" / "vl-01.m4a").unlink()
    assert run(proj) == 1
    assert "не найден" in capsys.readouterr().out


def test_tmp_removed_on_ffmpeg_failure(proj, capsys):
    # Портим аудиофайл: ffmpeg упадёт на декодировании входа
    bad = proj / "episodes" / "ep01" / "audio" / "voice" / "vl-01.m4a"
    bad.write_bytes(b"not an audio file")
    assert run(proj) == 1
    audio_dir = proj / "episodes" / "ep01" / "audio"
    assert not (audio_dir / "mix.tmp.m4a").exists()
    assert not (audio_dir / "mix.m4a").exists()
    assert "ОШИБКА ffmpeg" in capsys.readouterr().out


def test_two_music_cues_exercise_amix(proj, make_tone):
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"] = []
    data["sfx"] = []
    data["music_cues"].append({"id": "mus-02", "prompt": "calm2",
                               "duration": 1, "segment": 2, "offset": 0})
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    f = make_tone(ep / "audio" / "music" / "mus-02.m4a", 1.0)
    m = Manifest(proj / "manifest.json")
    m.add("ep01/audio/mus-02", kind="music")
    m.set_status("ep01/audio/mus-02", "generating")
    m.set_status("ep01/audio/mus-02", "generated", file=str(f))
    m.set_status("ep01/audio/mus-02", "done")
    m.save()
    assert run(proj) == 0
    assert mix_path(proj).exists()
    assert abs(probe_duration(mix_path(proj)) - 4.0) < 0.3
