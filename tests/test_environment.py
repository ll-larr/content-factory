"""Проверка окружения: что сломается на этой машине и чем это ставится.

Продукт отдают человеку, у которого может не быть ни ffmpeg, ни node. Без этой
проверки он узнавал бы о них трейсбеком посреди сборки — уже после того, как за
съёмку заплатили.
"""
from pathlib import Path

import pytest

from factory import environment, webapp

REPO = Path(__file__).resolve().parents[1]


def test_every_requirement_says_what_breaks_and_how_to_install():
    """Строка «ffmpeg не найден» без «что сломается» ничего не решает."""
    for spec in environment.REQUIREMENTS:
        assert spec["why"] and spec["breaks"], spec["id"]
        assert set(spec["install"]) == {"windows", "macos", "linux"}, spec["id"]
        assert all(spec["install"].values()), spec["id"]


def test_check_reports_montage_dependencies_too():
    """node стоит, а `npx remotion` всё равно падает: пакеты ставятся отдельно."""
    ids = {row["id"] for row in environment.check(REPO)}
    assert "montage_modules" in ids


def test_found_tool_carries_its_path():
    rows = {row["id"]: row for row in environment.check(REPO)}
    # ffmpeg обязателен для тестов фазы 2 (conftest), значит он тут есть.
    assert rows["ffmpeg"]["found"] is True
    assert rows["ffmpeg"]["path"]


def test_missing_tool_is_explained_with_the_right_installer(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    lines = environment.problems(REPO, os_name="macos")

    assert any("brew install ffmpeg" in line for line in lines)
    assert any("не будет работать" in line for line in lines)


def test_installer_hint_follows_the_operating_system(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    windows = "\n".join(environment.problems(REPO, os_name="windows"))
    linux = "\n".join(environment.problems(REPO, os_name="linux"))

    assert "winget" in windows and "winget" not in linux
    assert "apt install" in linux


def test_missing_montage_modules_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/" + name)

    lines = environment.problems(tmp_path, os_name="linux")

    assert len(lines) == 1
    assert "npm install --prefix montage" in lines[0]


def test_nothing_missing_means_no_lines():
    assert environment.problems(REPO) == []


def test_version_failure_does_not_break_the_check(monkeypatch):
    """Версия — справка человеку, а не условие работы."""
    def boom(*a, **k):
        raise OSError("нет доступа")

    monkeypatch.setattr("subprocess.run", boom)
    rows = {row["id"]: row for row in environment.check(REPO)}

    assert rows["ffmpeg"]["found"] is True
    assert rows["ffmpeg"]["version"] == ""


def test_panel_says_the_same_thing_as_the_cli():
    """Панель и render.py обязаны называть одни и те же причины."""
    assert webapp.environment_state(REPO) == environment.check(REPO)


def test_render_refuses_before_touching_the_project(monkeypatch, tmp_path, capsys):
    """Отказ приходит ДО чтения проекта: иначе он тонет в чужих ошибках."""
    import render

    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.chdir(tmp_path)
    code = render.main(["--project", str(tmp_path / "нет-такого"),
                        "--episode", "ep01"])

    out = capsys.readouterr().out
    assert code == 1
    assert "НЕ ХВАТАЕТ ИНСТРУМЕНТОВ" in out
    assert "ПРОЕКТ НЕ ПРОШЁЛ" not in out


def test_dry_run_does_not_need_the_tools(monkeypatch, tmp_path, capsys):
    """`--dry-run` печатает лист и ничего не запускает — ему инструменты не нужны."""
    import render

    monkeypatch.setattr("shutil.which", lambda name: None)
    code = render.main(["--project", str(tmp_path / "нет-такого"),
                        "--episode", "ep01", "--dry-run"])

    assert "НЕ ХВАТАЕТ ИНСТРУМЕНТОВ" not in capsys.readouterr().out
    assert code == 1          # проекта нет — но отказ уже про проект
