"""Тесты плейсхолдеров в промптах кадров (спека 2026-08-02 §10)."""
import pytest

from factory.artifact import Artifact, save_artifact
from factory.prompts import PromptError, canonical_block, expand_prompt, prompt_problems

STYLE = """Общий стиль сериала.

<!-- canonical:style -->
flat 2D cartoon, thick outlines, saturated palette
<!-- /canonical:style -->
"""

MURZIK = """Рыжий кот-астронавт.

<!-- canonical:appearance -->
orange tabby cat, white chest patch, blue spacesuit
<!-- /canonical:appearance -->
"""


@pytest.fixture
def proj(tmp_path):
    save_artifact(Artifact(path=tmp_path / "bible" / "style-guide.md",
                           meta={"kind": "style-guide", "status": "approved"},
                           body=STYLE))
    save_artifact(Artifact(path=tmp_path / "bible" / "characters" / "murzik.md",
                           meta={"kind": "character", "status": "approved"},
                           body=MURZIK))
    return tmp_path


def test_canonical_block_extracted(proj):
    got = canonical_block(proj / "bible" / "style-guide.md", "style")
    assert got == "flat 2D cartoon, thick outlines, saturated palette"


def test_canonical_block_missing_raises(proj):
    with pytest.raises(PromptError, match="canonical:appearance"):
        canonical_block(proj / "bible" / "style-guide.md", "appearance")


def test_expand_substitutes_style_and_character(proj):
    got = expand_prompt("{{style}} {{char:murzik}} presses a button", proj)
    assert "flat 2D cartoon" in got
    assert "orange tabby cat" in got
    assert "{{" not in got


def test_expand_unknown_character_raises(proj):
    with pytest.raises(PromptError, match="barsik"):
        expand_prompt("{{char:barsik}} sleeps", proj)


def test_expand_unknown_placeholder_raises(proj):
    with pytest.raises(PromptError, match="mood"):
        expand_prompt("{{mood}} scene", proj)


def test_problems_flags_missing_style(proj):
    problems = prompt_problems("{{char:murzik}} sits", proj, [])
    assert any("{{style}}" in p for p in problems)


def test_problems_flags_character_without_ref(proj):
    problems = prompt_problems("{{style}} {{char:murzik}} sits", proj, [])
    assert any("murzik" in p and "refs" in p for p in problems)


def test_problems_empty_when_everything_declared(proj):
    refs = ["bible/characters/murzik-ref.png"]
    assert prompt_problems("{{style}} {{char:murzik}} sits", proj, refs) == []


def test_problems_flags_unapproved_character(proj):
    card = proj / "bible" / "characters" / "murzik.md"
    save_artifact(Artifact(path=card, meta={"kind": "character", "status": "draft"},
                           body=MURZIK))
    problems = prompt_problems("{{style}} {{char:murzik}} sits", proj,
                               ["bible/characters/murzik-ref.png"])
    assert any("не одобрен" in p for p in problems)
