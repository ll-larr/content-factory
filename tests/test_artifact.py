"""Тесты текстового артефакта пре-продакшна (спека 2026-08-02 §4)."""
import pytest

from factory.artifact import (Artifact, ArtifactError, body_sha, load_artifact,
                              save_artifact)

SAMPLE = """---
kind: idea
status: draft
---

Космические коты исследуют заброшенную станцию.
"""


def test_load_reads_meta_and_body(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text(SAMPLE, encoding="utf-8")
    art = load_artifact(p)
    assert art.meta["kind"] == "idea"
    assert art.meta["status"] == "draft"
    assert "заброшенную станцию" in art.body


def test_save_load_round_trip(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text(SAMPLE, encoding="utf-8")
    art = load_artifact(p)
    art.meta["status"] = "approved"
    save_artifact(art)

    again = load_artifact(p)
    assert again.meta["status"] == "approved"
    assert again.sha == art.sha, "перезапись frontmatter не должна менять хеш тела"


def test_sha_ignores_line_endings(tmp_path):
    """CRLF на Windows не должен менять хеш — иначе файл 'устареет' сам собой."""
    assert body_sha("a\r\nb") == body_sha("a\nb")


def test_sha_ignores_edge_whitespace():
    assert body_sha("\n  текст  \n\n") == body_sha("текст")


def test_sha_changes_with_content():
    assert body_sha("текст один") != body_sha("текст два")


def test_missing_frontmatter_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("просто текст без шапки", encoding="utf-8")
    with pytest.raises(ArtifactError, match="frontmatter"):
        load_artifact(p)


def test_unclosed_frontmatter_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("---\nkind: idea\nтекст", encoding="utf-8")
    with pytest.raises(ArtifactError, match="не закрыт"):
        load_artifact(p)


def test_frontmatter_not_a_mapping_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("---\n- a\n- b\n---\nтекст", encoding="utf-8")
    with pytest.raises(ArtifactError, match="словар"):
        load_artifact(p)


def test_save_creates_parent_dirs(tmp_path):
    art = Artifact(path=tmp_path / "bible" / "characters" / "murzik.md",
                   meta={"kind": "character"}, body="рыжий кот")
    save_artifact(art)
    assert art.path.exists()


def test_save_keeps_cyrillic_readable(tmp_path):
    art = Artifact(path=tmp_path / "idea.md",
                   meta={"kind": "idea", "note": "космос"}, body="тело")
    save_artifact(art)
    assert "космос" in art.path.read_text(encoding="utf-8")
