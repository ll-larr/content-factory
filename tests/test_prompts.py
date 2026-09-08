"""Тесты плейсхолдеров в промптах кадров (спека 2026-08-02 §10)."""
import pytest

from factory.artifact import (Artifact, ArtifactError, body_sha, canonical_block,
                              has_canonical, save_artifact)
from factory.prompts import PromptError, expand_prompt, prompt_problems

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
                           meta={"kind": "style-guide", "status": "approved",
                                 "content_sha": body_sha(STYLE)},
                           body=STYLE))
    save_artifact(Artifact(path=tmp_path / "bible" / "characters" / "murzik.md",
                           meta={"kind": "character", "status": "approved",
                                 "content_sha": body_sha(MURZIK)},
                           body=MURZIK))
    return tmp_path


def test_canonical_block_extracted(proj):
    got = canonical_block(proj / "bible" / "style-guide.md", "style")
    assert got == "flat 2D cartoon, thick outlines, saturated palette"


def test_canonical_block_missing_raises(proj):
    """Разбор блока переехал в factory.artifact (разрыв цикла импортов), поэтому
    и ошибка теперь его — ArtifactError."""
    with pytest.raises(ArtifactError, match="canonical:appearance"):
        canonical_block(proj / "bible" / "style-guide.md", "appearance")


def test_expand_still_raises_prompt_error_when_block_missing(proj):
    """Контракт разворачивания переезд не изменил: наружу летит PromptError.

    canonical_block теперь поднимает ArtifactError, и без обёртки он утёк бы мимо
    `except PromptError` в generate_batch — то есть трейсбеком на платной стадии.
    """
    save_artifact(Artifact(path=proj / "bible" / "style-guide.md",
                           meta={"kind": "style-guide", "status": "approved"},
                           body="без всякого блока"))
    with pytest.raises(PromptError, match="canonical:style"):
        expand_prompt("{{style}} cat", proj)


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


def test_empty_character_name_is_flagged(proj):
    """{{char:}} узкий regex не видит вовсе — без отдельной проверки такой текст
    уехал бы провайдеру буквально."""
    problems = prompt_problems("{{style}} {{char:}} sits", proj, [])
    assert any("char:" in p for p in problems), problems


def test_style_with_argument_is_flagged_by_gate(proj):
    """{{style:foo}} раньше проходил гейт и падал уже в expand_prompt — то есть
    после того, как смета показана человеку."""
    problems = prompt_problems("{{style:foo}} cat", proj, [])
    assert any("не принимает аргумент" in p for p in problems), problems


def test_placeholder_inside_canonical_block_is_rejected(tmp_path):
    """Блок стиля с {{...}} внутри: подстановка одним проходом не пересматривает
    вставленное, и фигурные скобки уехали бы провайдеру буквально."""
    body = "<!-- canonical:style -->flat 2D {{char:murzik}}<!-- /canonical:style -->"
    save_artifact(Artifact(path=tmp_path / "bible" / "style-guide.md",
                           meta={"kind": "style-guide", "status": "approved",
                                 "content_sha": body_sha(body)}, body=body))
    with pytest.raises(PromptError, match="после разворачивания"):
        expand_prompt("{{style}} cat", tmp_path)


def test_has_canonical_does_not_swallow_programmer_errors(tmp_path):
    """Голый `except Exception` прятал и ошибки программиста: гейт молча отвечал
    «блока нет» на сломанный вызов вместо того, чтобы упасть и показать причину."""
    body = "<!-- canonical:style -->flat 2D<!-- /canonical:style -->"
    path = tmp_path / "bible" / "style-guide.md"
    save_artifact(Artifact(path=path, meta={"kind": "style-guide"}, body=body))
    assert has_canonical(path, "style") is True
    with pytest.raises(TypeError):
        has_canonical(path, None)


def test_has_canonical_false_on_broken_artifact(tmp_path):
    """Битый артефакт по-прежнему не роняет гейт: его дело — вернуть список
    проблем, а не упасть."""
    path = tmp_path / "bible" / "style-guide.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("нет никакого frontmatter", encoding="utf-8")
    assert has_canonical(path, "style") is False


def test_canonical_name_is_escaped(tmp_path):
    """Имя блока подставлялось в регулярку без экранирования: разряженное ружьё —
    имя со спецсимволом молча совпало бы не с тем блоком."""
    body = "<!-- canonical:a.c -->точка<!-- /canonical:a.c -->"
    path = tmp_path / "bible" / "style-guide.md"
    save_artifact(Artifact(path=path, meta={"kind": "style-guide"}, body=body))
    assert has_canonical(path, "a.c") is True
    assert has_canonical(path, "abc") is False
