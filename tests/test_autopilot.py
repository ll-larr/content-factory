"""Автономный режим ведёт конвейер на СЕРВЕРЕ, а не во вкладке браузера.

Человек включил режим и ушёл — закрытая вкладка не должна останавливать
конвейер, а ручных одобрений в этом режиме нет вовсе: их ставит сам режим,
помечая, что чекпоинт не смотрел живой человек.
"""
import json
from pathlib import Path

import pytest

from factory import autopilot, webapp

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"
REPO_ROOT = Path(__file__).resolve().parents[1]

PROJECT = {
    "name": "pilot", "type": "animated_series", "theme": "маяк",
    "audience": "9-12", "episodes": 1, "episode_duration_sec": 60,
    "language": "ru", "autonomy": "full",
    "models": {"image": {"model": "z_image_turbo", "provider": "wavespeed"},
               "video": {"model": "seedance_2_0", "provider": "wavespeed"}},
}


class FakeRunner:
    """Реестр задач без процессов: запоминает, что попросили запустить."""

    def __init__(self):
        self.started = []

    def is_running(self):
        return False

    def start(self, cmd, meta=None):
        self.started.append({"cmd": list(cmd), "meta": dict(meta or {})})
        return {"id": "t1", **(meta or {})}


@pytest.fixture
def root(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / "pilot" / "episodes" / "ep01").mkdir(parents=True)
    (projects / "pilot" / "project.json").write_text(
        json.dumps(PROJECT, ensure_ascii=False), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return projects


def done_task(stage="script", episode="ep01", status="done"):
    return {"kind": "text", "project": "pilot", "episode": episode,
            "stage": stage, "status": status, "lines": []}


def test_next_stage_starts_without_a_browser(root, monkeypatch):
    """Шаг конвейера продолжает СЕРВЕР: вкладка может быть закрыта."""
    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "next_stage",
                        lambda pdir: ("factcheck", "ep01"))

    autopilot.step(runner, root, done_task(), repo_root=REPO_ROOT)

    assert runner.started, "следующая стадия не запущена"
    assert runner.started[0]["meta"]["stage"] == "factcheck"


def test_manual_mode_is_not_driven(root, monkeypatch):
    path = root / "pilot" / "project.json"
    brief = json.loads(path.read_text(encoding="utf-8"))
    brief["autonomy"] = "checkpoints"
    path.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: ("factcheck", "ep01"))

    autopilot.step(runner, root, done_task(), repo_root=REPO_ROOT)

    assert runner.started == []


def test_failed_stage_stops_the_run(root, monkeypatch):
    """Отказавшая стадия — стоп: гнать дальше по сломанному входу нечего."""
    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: ("factcheck", "ep01"))

    autopilot.step(runner, root, done_task(status="failed"), repo_root=REPO_ROOT)

    assert runner.started == []


def test_repeat_of_the_same_step_stops_the_run(root, monkeypatch):
    """Резолвер просит то же самое — значит ждут человека, а не машину."""
    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: ("script", "ep01"))

    autopilot.step(runner, root, done_task(stage="script"), repo_root=REPO_ROOT)

    assert runner.started == []


def test_texts_are_approved_by_the_mode_itself(root, monkeypatch):
    """Ручных одобрений в автономном режиме нет: их ставит сам режим."""
    idea = root / "pilot" / "bible" / "idea.md"
    idea.parent.mkdir(parents=True, exist_ok=True)
    idea.write_text("---\nkind: idea\nstatus: draft\n---\nмаяк\n", encoding="utf-8")
    approved = []

    def fake_approve(project_dir, rel, *, auto=False):
        approved.append((rel, auto))
        return {"path": rel, "state": "approved"}

    monkeypatch.setattr(autopilot, "approve_artifact", fake_approve)
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: None)

    autopilot.step(FakeRunner(), root, done_task(stage="story", episode=None),
                   repo_root=REPO_ROOT)

    assert ("bible/idea.md", True) in approved, "одобрено и помечено как авто"


def test_gate_refusing_approval_does_not_stop_the_run(root, monkeypatch):
    """Сценарий без проверки фактов одобрить нельзя — и это не остановка.

    Следующий шаг резолвера как раз и есть проверка: живой прогон 2026-09-09
    встал именно здесь, приняв отказ гейта за отказ конвейера.
    """
    script = root / "pilot" / "episodes" / "ep01" / "script.md"
    script.write_text("---\nkind: script\nstatus: draft\n---\nтекст\n",
                      encoding="utf-8")

    def refusing(project_dir, rel, *, auto=False):
        raise webapp.WebappError("нельзя одобрить — факты не проверены")

    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "approve_artifact", refusing)
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: ("factcheck", "ep01"))

    autopilot.step(runner, root, done_task(), repo_root=REPO_ROOT)

    assert runner.started and runner.started[0]["meta"]["stage"] == "factcheck"


def test_generated_media_is_accepted_by_the_mode(root, monkeypatch):
    """Кадр, ждущий человека, в автономном режиме принимает сам режим."""
    from factory.manifest import Manifest

    manifest = Manifest(root / "pilot" / "manifest.json")
    manifest.add("ep01/storyboard/001", kind="frame")
    manifest.set_status("ep01/storyboard/001", "generating")
    manifest.set_status("ep01/storyboard/001", "generated")
    manifest.save()
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: None)

    autopilot.step(FakeRunner(), root, done_task(stage="storyboard"),
                   repo_root=REPO_ROOT)

    item = Manifest(root / "pilot" / "manifest.json").get("ep01/storyboard/001")
    assert item["status"] == "done"
    assert item.get("accepted_by") == "auto", "видно, что человек не смотрел"


def test_paid_stage_is_started_by_its_runnable_name(root, monkeypatch):
    """Резолвер зовёт кадры `storyboard_generate`, а CLI знает `storyboard`."""
    runner = FakeRunner()
    monkeypatch.setattr(autopilot, "next_stage",
                        lambda pdir: ("storyboard_generate", "ep01"))

    autopilot.step(runner, root, done_task(stage="storyboard"), repo_root=REPO_ROOT)

    assert runner.started[0]["meta"]["stage"] == "storyboard"
    assert "--yes" in runner.started[0]["cmd"]


# --- ручной старт автономного прогона --------------------------------------

def test_kick_starts_the_run_from_a_standing_project(root, monkeypatch):
    """Кнопка «Запустить конвейер» просит сервер начать — и он начинает.

    Первый шаг может упираться в неодобренный артефакт: резолвер молчит, пока
    его ждут, и без одобрения прогон не начался бы вовсе.
    """
    script = root / "pilot" / "episodes" / "ep01" / "script.md"
    script.write_text("---\nkind: script\nstatus: draft\n---\nтекст\n",
                      encoding="utf-8")
    approved = []
    monkeypatch.setattr(autopilot, "approve_artifact",
                        lambda pdir, rel, auto=False: approved.append(rel))
    steps = iter([("characters", "ep01")])
    monkeypatch.setattr(autopilot, "next_stage", lambda pdir: next(steps))
    runner = FakeRunner()

    result = autopilot.kick(runner, root, "pilot", repo_root=REPO_ROOT)

    assert approved == ["episodes/ep01/script.md"]
    assert result["started"]["stage"] == "characters"
    assert any("одобрено" in line for line in result["lines"])


def test_kick_refuses_in_manual_mode(root):
    path = root / "pilot" / "project.json"
    brief = json.loads(path.read_text(encoding="utf-8"))
    brief["autonomy"] = "checkpoints"
    path.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(webapp.WebappError, match="ручн"):
        autopilot.kick(FakeRunner(), root, "pilot", repo_root=REPO_ROOT)
