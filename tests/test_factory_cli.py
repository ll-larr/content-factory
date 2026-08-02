"""Тесты CLI пре-продакшна (спека 2026-08-02 §6)."""
import json

import pytest

import factory_cli_entry as fc  # см. шаг 3: тонкая обёртка над scripts/factory.py
from factory.artifact import Artifact, load_artifact, save_artifact
from factory.preprod import artifact_state


def _write_body(path, text):
    """Дозаполнить тело уже заскаффолженного артефакта перед одобрением.

    Отступление от буквального текста брифа (третий такой случай в этом плане —
    см. .superpowers/sdd/pp-task-4-report.md): `init` намеренно создаёт артефакты
    с пустым телом (спека §6: "пустые артефакты со status: draft"), а `approve`
    намеренно отказывает на пустом теле — одобрять нечего не написанное бессмысленно.
    Тесты из брифа `test_approve_records_dependency_hashes` и
    `test_check_opens_after_approve` одобряли идею/арку сразу после `init`, то есть
    пустыми, и полагались на то, что `approve` это пропустит. Так реальный человек
    не работает: он сперва пишет текст, потом одобряет. Дозаполняем тело здесь же,
    вместо того чтобы тихо ослаблять проверку в `cmd_approve`."""
    art = load_artifact(path)
    art.body = text
    save_artifact(art)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / "projects" / "pilot").mkdir(parents=True)
    (tmp_path / "projects" / "pilot" / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 2, "episode_duration_sec": 10,
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path / "projects" / "pilot"


def run(*args):
    return fc.main([str(a) for a in args])


def test_init_creates_tree_with_drafts(proj):
    assert run("init", "--project", proj) == 0
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"):
        assert artifact_state(proj, proj / rel) == "draft"


def test_init_is_idempotent_and_keeps_content(proj):
    run("init", "--project", proj)
    art = load_artifact(proj / "bible" / "idea.md")
    art.body = "уже написанная идея"
    from factory.artifact import save_artifact
    save_artifact(art)

    assert run("init", "--project", proj) == 0
    assert "уже написанная идея" in load_artifact(proj / "bible" / "idea.md").body


def test_check_returns_3_when_gate_closed(proj):
    run("init", "--project", proj)
    assert run("check", "--project", proj, "--stage", "script", "--episode", "ep01") == 3


def test_approve_sets_status_and_hashes(proj):
    run("init", "--project", proj)
    art = load_artifact(proj / "bible" / "idea.md")
    art.body = "идея"
    from factory.artifact import save_artifact
    save_artifact(art)

    assert run("approve", "--project", proj, "bible/idea.md") == 0
    saved = load_artifact(proj / "bible" / "idea.md")
    assert saved.meta["status"] == "approved"
    assert saved.meta["content_sha"] == saved.sha
    assert "approved_at" in saved.meta


def test_approve_records_dependency_hashes(proj):
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    run("approve", "--project", proj, "bible/idea.md")
    _write_body(proj / "bible" / "season-arc.md", "арка")
    assert run("approve", "--project", proj, "bible/season-arc.md") == 0
    arc = load_artifact(proj / "bible" / "season-arc.md")
    deps = {d["path"]: d["sha"] for d in arc.meta["depends_on"]}
    assert deps["bible/idea.md"] == load_artifact(proj / "bible" / "idea.md").sha


def test_approve_refuses_when_dependency_missing(proj):
    """Одобрять сценарий, у которого нет идеи, бессмысленно — и падать на этом
    тоже нельзя (находка ревью задачи 2)."""
    run("init", "--project", proj)
    from factory.artifact import Artifact, save_artifact
    save_artifact(Artifact(path=proj / "episodes" / "ep01" / "script.md",
                           meta={"kind": "script", "status": "draft"},
                           body="сценарий"))
    (proj / "bible" / "idea.md").unlink()
    assert run("approve", "--project", proj, "episodes/ep01/script.md") == 1


def test_approve_refuses_missing_file(proj):
    run("init", "--project", proj)
    assert run("approve", "--project", proj, "bible/nope.md") == 1


def test_approve_refuses_empty_body(proj):
    """Дописано сверх брифа (самопроверка задачи 4): ни один тест брифа не проверял
    отказ на пустом теле напрямую, хотя сама проверка есть в эталонном коде и
    явно требуется самопроверкой задачи. `init` намеренно оставляет тело пустым
    (спека §6), поэтому одобрение сразу после init обязано отказать."""
    run("init", "--project", proj)
    assert run("approve", "--project", proj, "bible/idea.md") == 1
    assert artifact_state(proj, proj / "bible" / "idea.md") == "draft"


def test_approve_refuses_when_dependency_is_unparseable(proj):
    """Дописано сверх брифа (самопроверка задачи 4): зависимость есть на диске, но
    без frontmatter — ArtifactError не должен вылететь наружу необработанным, это
    ровно тот же класс проблемы, что и отсутствующая зависимость выше, только про
    файл, который есть, но не читается."""
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    run("approve", "--project", proj, "bible/idea.md")
    _write_body(proj / "bible" / "season-arc.md", "арка")
    save_artifact(Artifact(path=proj / "episodes" / "ep01" / "script.md",
                           meta={"kind": "script", "status": "draft"},
                           body="сценарий"))
    (proj / "bible" / "idea.md").write_text("файл без frontmatter\n", encoding="utf-8")
    assert run("approve", "--project", proj, "episodes/ep01/script.md") == 1


def test_check_opens_after_approve(proj):
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    run("approve", "--project", proj, "bible/idea.md")
    _write_body(proj / "bible" / "season-arc.md", "арка")
    run("approve", "--project", proj, "bible/season-arc.md")
    assert run("check", "--project", proj, "--stage", "script", "--episode", "ep01") == 0


def test_next_prints_story_first(proj, capsys):
    run("init", "--project", proj)
    assert run("next", "--project", proj) == 0
    assert "story" in capsys.readouterr().out


def test_status_lists_every_artifact(proj, capsys):
    run("init", "--project", proj)
    run("status", "--project", proj)
    out = capsys.readouterr().out
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"):
        assert rel in out


def test_approve_refuses_broken_target(proj):
    """approve обязан отказать с кодом 1, а не упасть трейсбеком, если файл,
    который он одобряет, не разбирается."""
    run("init", "--project", proj)
    (proj / "bible" / "idea.md").write_text("текст без frontmatter\n", encoding="utf-8")
    assert run("approve", "--project", proj, "bible/idea.md") == 1


def test_status_survives_broken_artifact(proj, capsys):
    run("init", "--project", proj)
    (proj / "bible" / "idea.md").write_text("текст без frontmatter\n", encoding="utf-8")
    assert run("status", "--project", proj) == 0
    assert "broken" in capsys.readouterr().out
