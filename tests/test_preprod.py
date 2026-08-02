"""Тесты состояния артефактов и гейтов пре-продакшна (спека 2026-08-02 §5)."""
import pytest

from factory.artifact import Artifact, body_sha, load_artifact, save_artifact
from factory.preprod import artifact_state, dependencies


def write(path, kind, body, status="draft", **extra):
    """Записать артефакт; при status='approved' проставить корректные хеши."""
    meta = {"kind": kind, "status": status, **extra}
    if status == "approved":
        meta["content_sha"] = body_sha(body)
    art = Artifact(path=path, meta=meta, body=body)
    save_artifact(art)
    return art


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "bible").mkdir()
    return tmp_path


def test_missing_file(proj):
    assert artifact_state(proj, proj / "bible" / "idea.md") == "missing"


def test_draft(proj):
    write(proj / "bible" / "idea.md", "idea", "идея")
    assert artifact_state(proj, proj / "bible" / "idea.md") == "draft"


def test_approved(proj):
    write(proj / "bible" / "idea.md", "idea", "идея", status="approved")
    assert artifact_state(proj, proj / "bible" / "idea.md") == "approved"


def test_stale_self_when_body_edited_after_approval(proj):
    p = proj / "bible" / "idea.md"
    write(p, "idea", "идея", status="approved")
    art = load_artifact(p)
    art.body = "идея, но переписанная"
    save_artifact(art)
    assert artifact_state(proj, p) == "stale_self"


def test_stale_deps_when_dependency_edited(proj):
    idea = proj / "bible" / "idea.md"
    write(idea, "idea", "идея", status="approved")
    arc = proj / "bible" / "season-arc.md"
    write(arc, "season-arc", "сюжет", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": body_sha("идея")}])
    assert artifact_state(proj, arc) == "approved"

    art = load_artifact(idea)
    art.body = "совсем другая идея"
    save_artifact(art)
    assert artifact_state(proj, arc) == "stale_deps"


def test_stale_deps_when_dependency_deleted(proj):
    arc = proj / "bible" / "season-arc.md"
    write(arc, "season-arc", "сюжет", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": body_sha("идея")}])
    assert artifact_state(proj, arc) == "stale_deps"


def test_stale_deps_when_dependency_is_unparseable(proj):
    arc = proj / "bible" / "season-arc.md"
    write(arc, "season-arc", "сюжет", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": body_sha("идея")}])
    idea = proj / "bible" / "idea.md"
    idea.write_text("просто текст, без YAML-frontmatter\n", encoding="utf-8")
    assert artifact_state(proj, arc) == "stale_deps"


def test_dependencies_of_script(proj):
    art = write(proj / "episodes" / "ep01" / "script.md", "script", "сценарий")
    assert [p.name for p in dependencies(proj, art)] == ["idea.md", "season-arc.md"]


def test_dependencies_of_character_include_scripts_mentioning_it(proj):
    write(proj / "episodes" / "ep01" / "script.md", "script", "Мурзик жмёт кнопку")
    write(proj / "episodes" / "ep02" / "script.md", "script", "Барсик спит")
    art = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    got = [p.as_posix().split("projects/")[-1] for p in dependencies(proj, art)]
    assert any("ep01/script.md" in g for g in got)
    assert not any("ep02/script.md" in g for g in got), \
        "Барсик не упомянут — сценарий ep02 не зависимость Мурзика"


def test_dependencies_of_character_skips_unparseable_script(proj):
    broken = proj / "episodes" / "ep01" / "script.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("Мурзик жмёт кнопку, но файл без frontmatter\n", encoding="utf-8")
    write(proj / "episodes" / "ep02" / "script.md", "script", "Мурзик жмёт кнопку")
    art = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    got = [p.as_posix() for p in dependencies(proj, art)]
    assert not any("ep01/script.md" in g for g in got), \
        "битый сценарий (без frontmatter) пропущен, а не роняет dependencies()"
    assert any("ep02/script.md" in g for g in got)


def test_dependencies_of_idea_is_empty(proj):
    art = write(proj / "bible" / "idea.md", "idea", "идея")
    assert dependencies(proj, art) == []
