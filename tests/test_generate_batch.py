"""Тесты батч-генератора generate_batch.py (спека §8)."""
import json
from pathlib import Path

import pytest

import generate_batch as gb
from factory.manifest import Manifest

KLING_CARD = (
    "---\nid: kling3_0\ntype: video\nfamily: kling\nstatus: verified\n"
    "supports_start_end_frame: true\nnative_audio: true\n"
    "max_clip_seconds: 10\ncost_tier: medium\n---\n# Kling\n")


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Мини-проект: 3 кадра, 2 отрезка; CWD = tmp_path (как корень репо)."""
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
    kdir = tmp_path / "knowledge" / "video"
    kdir.mkdir(parents=True)
    (kdir / "kling3_0.md").write_text(KLING_CARD, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return pdir


def fake_hf(monkeypatch):
    calls = {"submitted": []}
    monkeypatch.setattr(gb.hf, "estimate", lambda m, p: 2.0)

    def submit(model, params):
        calls["submitted"].append(params)
        return f"job-{len(calls['submitted'])}"

    monkeypatch.setattr(gb.hf, "submit", submit)
    monkeypatch.setattr(gb.hf, "wait", lambda j: {"status": "completed"})

    def download(job_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"x")
        return Path(dest)

    monkeypatch.setattr(gb.hf, "download", download)
    return calls


def run(proj, stage):
    return gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", stage, "--yes"])


def test_happy_path_storyboard(proj, monkeypatch):
    calls = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(calls["submitted"]) == 3
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "done"
    assert (proj / "episodes" / "ep01" / "storyboard" / "001.png").exists()


def test_resume_skips_done(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert calls2["submitted"] == []  # ничего не сгенерировано повторно


def test_segments_pass_start_end_frames(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(calls2["submitted"]) == 2
    assert "start_frame" in calls2["submitted"][0]
    assert "end_frame" in calls2["submitted"][0]


def test_skeleton_card_blocks_segments(proj, monkeypatch):
    fake_hf(monkeypatch)
    card = Path("knowledge/video/kling3_0.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run(proj, "segments") == 2  # валидация остановила ДО траты кредитов


def test_higgsfied_error_returns_to_pending(proj, monkeypatch):
    """Технический сбой HiggsfieldError возвращает item в pending и main → 1."""
    monkeypatch.setattr(gb.hf, "estimate", lambda m, p: 2.0)
    monkeypatch.setattr(gb.hf, "submit",
                        lambda m, p: (_ for _ in ()).throw(
                            gb.hf.HiggsfieldError("сеть упала")))
    run_result = run(proj, "storyboard")
    assert run_result == 1  # сбои были
    m = Manifest(proj / "manifest.json")
    # После сбоя все элементы должны быть в pending (для повторной попытки)
    assert m.get("ep01/storyboard/001")["status"] == "pending"
    assert m.get("ep01/storyboard/002")["status"] == "pending"
    assert m.get("ep01/storyboard/003")["status"] == "pending"
    # attempts должен быть инкрементирован (первый прогон = 1)
    assert m.get("ep01/storyboard/001")["attempts"] == 1


def test_retry_after_failure_runs_only_failed(proj, monkeypatch):
    """Повторный прогон после сбоя запускает только упавшие (pending) элементы."""
    # Первый прогон: сбой на каждом submit
    monkeypatch.setattr(gb.hf, "estimate", lambda m, p: 2.0)
    monkeypatch.setattr(gb.hf, "submit",
                        lambda m, p: (_ for _ in ()).throw(
                            gb.hf.HiggsfieldError("сбой")))
    run(proj, "storyboard")  # все вернулись в pending

    # Второй прогон: нормальная работа
    calls2 = fake_hf(monkeypatch)
    result2 = run(proj, "storyboard")
    assert result2 == 0
    # Все 3 кадра должны быть запущены повторно (все были pending)
    assert len(calls2["submitted"]) == 3


def test_skeleton_blocks_before_estimate(proj, monkeypatch):
    """Скелетная карточка блокирует segments ДО вызова estimate (кредиты не тратятся)."""
    estimate_called = []
    monkeypatch.setattr(gb.hf, "estimate",
                        lambda m, p: estimate_called.append(1) or 2.0)
    card = Path("knowledge/video/kling3_0.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    result = run(proj, "segments")
    assert result == 2
    assert estimate_called == []  # estimate не должен вызываться


def test_recover_stuck_generating_item(proj, monkeypatch):
    """Элемент в статусе generating после прерывания восстанавливается в pending
    и обрабатывается следующим прогоном (регрессия: зависание после KeyboardInterrupt)."""
    # Создаём манифест вручную: один item застрял в generating
    m = Manifest(proj / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.save()

    calls = fake_hf(monkeypatch)
    result = run(proj, "storyboard")
    assert result == 0
    # Застрявший элемент должен был пройти submit и стать done
    assert any(True for _ in calls["submitted"])  # submit вызывался
    m2 = Manifest(proj / "manifest.json")
    assert m2.get("ep01/storyboard/001")["status"] == "done"


def test_job_id_persisted_when_wait_fails(proj, monkeypatch):
    """Если submit прошёл, а wait упал — job_id сохраняется в манифесте
    (регрессия: невозможно соотнести сбой с логами Higgsfield)."""
    monkeypatch.setattr(gb.hf, "estimate", lambda m, p: 2.0)

    def submit_ok(model, params):
        return "job-abc123"

    def wait_fail(job_id):
        raise gb.hf.HiggsfieldError("timeout")

    monkeypatch.setattr(gb.hf, "submit", submit_ok)
    monkeypatch.setattr(gb.hf, "wait", wait_fail)

    result = run(proj, "storyboard")
    assert result == 1  # были сбои
    m = Manifest(proj / "manifest.json")
    item = m.get("ep01/storyboard/001")
    assert item["status"] == "pending"
    assert item["job_id"] == "job-abc123"  # job_id сохранён несмотря на сбой
