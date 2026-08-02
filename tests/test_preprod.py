"""Тесты состояния артефактов и гейтов пре-продакшна (спека 2026-08-02 §5)."""
import json

import pytest

from factory.artifact import Artifact, body_sha, load_artifact, save_artifact
from factory.preprod import artifact_state, dependencies
from factory.preprod import episode_ids, next_stage, stage_gate


def write(path, kind, body, status="draft", **extra):
    """Записать артефакт; при status='approved' проставить корректные хеши."""
    meta = {"kind": kind, "status": status, **extra}
    if status == "approved":
        meta["content_sha"] = body_sha(body)
    art = Artifact(path=path, meta=meta, body=body)
    save_artifact(art)
    return art


CHAR_BODY = "<!-- canonical:appearance -->orange cat<!-- /canonical:appearance -->"
STYLE_BODY = "<!-- canonical:style -->flat 2D cartoon<!-- /canonical:style -->"


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


def test_dependencies_of_character_use_declared_cast(proj):
    """Состав серии берётся из объявленного characters, а не поиском имени по тексту:
    «Мурзик смотрит на фотографию Барсика» не делает Барсика участником сцены."""
    write(proj / "episodes" / "ep01" / "script.md", "script", "Мурзик жмёт кнопку",
          characters=["Мурзик"])
    write(proj / "episodes" / "ep02" / "script.md", "script",
          "Мурзик смотрит на фотографию Барсика", characters=["Мурзик"])
    art = write(proj / "bible" / "characters" / "Барсик.md", "character", "серый кот")
    got = [p.as_posix() for p in dependencies(proj, art)]
    assert not any("script.md" in g for g in got), \
        "Барсик нигде не объявлен — ни один сценарий не его зависимость"

    murzik = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    got = [p.as_posix() for p in dependencies(proj, murzik)]
    assert any("ep01/script.md" in g for g in got)
    assert any("ep02/script.md" in g for g in got)


def test_dependencies_of_character_skips_unparseable_script(proj):
    broken = proj / "episodes" / "ep01" / "script.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("файл без frontmatter\n", encoding="utf-8")
    write(proj / "episodes" / "ep02" / "script.md", "script", "текст",
          characters=["Мурзик"])
    art = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    got = [p.as_posix() for p in dependencies(proj, art)]
    assert not any("ep01/script.md" in g for g in got), \
        "битый сценарий (без frontmatter) пропущен, а не роняет dependencies()"
    assert any("ep02/script.md" in g for g in got)


def test_dependencies_of_character_survive_script_without_cast(proj):
    """Серия без персонажей технически возможна (заставка, титры) — не падать."""
    write(proj / "episodes" / "ep01" / "script.md", "script", "титры")
    art = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    assert [p.as_posix() for p in dependencies(proj, art) if "script.md" in p.as_posix()] == []


def test_dependencies_of_idea_is_empty(proj):
    art = write(proj / "bible" / "idea.md", "idea", "идея")
    assert dependencies(proj, art) == []


def make_project(tmp_path, episodes=2):
    (tmp_path / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": episodes, "episode_duration_sec": 10,
    }), encoding="utf-8")
    return tmp_path


def test_episode_ids_from_project(tmp_path):
    p = make_project(tmp_path, episodes=3)
    assert episode_ids(p) == ["ep01", "ep02", "ep03"]


def test_story_gate_open_on_fresh_project(tmp_path):
    p = make_project(tmp_path)
    assert stage_gate(p, "story") == []


def test_script_gate_blocked_without_approved_story(tmp_path):
    p = make_project(tmp_path)
    problems = stage_gate(p, "script", "ep01")
    assert len(problems) == 2
    assert all("idea.md" in x or "season-arc.md" in x for x in problems)


def test_script_gate_open_after_story_approved(tmp_path):
    p = make_project(tmp_path)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    assert stage_gate(p, "script", "ep01") == []


def test_characters_gate_requires_approved_script(tmp_path):
    p = make_project(tmp_path)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    assert stage_gate(p, "characters", "ep01") != []
    write(p / "episodes" / "ep01" / "script.md", "script", "текст", status="approved")
    assert stage_gate(p, "characters", "ep01") == []


def test_gate_reports_stale_differently_from_draft(tmp_path):
    p = make_project(tmp_path)
    idea = p / "bible" / "idea.md"
    write(idea, "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    art = load_artifact(idea)
    art.body = "переписал"
    save_artifact(art)
    problems = stage_gate(p, "script", "ep01")
    assert any("изменён после одобрения" in x for x in problems)


def test_next_stage_walks_all_episodes_in_order(tmp_path):
    p = make_project(tmp_path, episodes=2)
    assert next_stage(p) == ("story", None)

    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    write(p / "bible" / "style-guide.md", "style-guide", "стиль", status="approved")
    assert next_stage(p) == ("script", "ep01")

    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved",
          characters=["Мурзик"])
    assert next_stage(p) == ("characters", "ep01")

    # Дописано сверх брифа: в буквальном тексте теста резолвер ни разу не доходит
    # до конца эпизода, поэтому переход ep01 -> ep02 остаётся недоказанным, хотя
    # именно это (§7: "все эпизоды по порядку, не останавливаясь на первом") —
    # ядро задачи. Закрываем разрыв: доводим ep01 до конца и проверяем, что
    # резолвер продолжает со script следующего эпизода, а не останавливается.
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    assert next_stage(p) == ("storyboard", "ep01")

    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")
    assert next_stage(p) == ("script", "ep02")


def test_next_stage_none_when_nothing_left(tmp_path):
    p = make_project(tmp_path, episodes=1)
    for rel, kind in (("bible/idea.md", "idea"), ("bible/season-arc.md", "season-arc"),
                      ("bible/style-guide.md", "style-guide")):
        write(p / rel, kind, "текст", status="approved")
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")
    assert next_stage(p) is None


# --- Находка ревью: персонаж, введённый в поздней серии, проходил гейт без карточки ---

def _closed_story(p):
    """Одобрить story-артефакты, чтобы дойти до поэпизодных гейтов.

    Стайл-гайд несёт канонический блок: гейт storyboard его проверяет — без блока
    разворачивать {{style}} в промпте кадра нечем."""
    write(p / "bible/idea.md", "idea", "текст", status="approved")
    write(p / "bible/season-arc.md", "season-arc", "текст", status="approved")
    write(p / "bible/style-guide.md", "style-guide", STYLE_BODY, status="approved")


def test_new_character_in_later_episode_reopens_characters_stage(tmp_path):
    """ep01 закрыт, ep02 вводит Барсика без карточки: резолвер обязан позвать
    characters, а не проскочить к storyboard (иначе кадры второй серии уйдут в
    генерацию за деньги с персонажем без описания и референса)."""
    p = make_project(tmp_path, episodes=2)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "episodes" / "ep02" / "script.md", "script", "с2",
          status="approved", characters=["Мурзик", "Барсик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")

    assert next_stage(p) == ("characters", "ep02")


def test_storyboard_gate_names_character_without_card(tmp_path):
    p = make_project(tmp_path, episodes=2)
    _closed_story(p)
    write(p / "episodes" / "ep02" / "script.md", "script", "с2",
          status="approved", characters=["Мурзик", "Барсик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")

    problems = stage_gate(p, "storyboard", "ep02")
    assert any("Барсик" in x for x in problems), problems


def test_storyboard_gate_open_when_whole_cast_approved(tmp_path):
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    assert stage_gate(p, "storyboard", "ep01") == []


def test_characters_gate_blocked_while_card_is_draft(tmp_path):
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", "кот")
    problems = stage_gate(p, "characters", "ep01")
    assert any("Мурзик" in x for x in problems), problems


def test_storyboard_gate_survives_script_without_cast(tmp_path):
    """Серия без персонажей не должна упираться в «нет ни одной карточки»."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "титры", status="approved")
    assert stage_gate(p, "storyboard", "ep01") == []


def test_broken_artifact_reads_as_broken_not_draft(proj):
    """Битый файл — отдельное состояние. Сказать про него «не одобрен (draft)»
    значит послать человека одобрять то, что не читается."""
    p = proj / "bible" / "idea.md"
    p.write_text("текст без frontmatter\n", encoding="utf-8")
    assert artifact_state(proj, p) == "broken"


def test_gate_names_broken_artifact_readably(tmp_path):
    p = make_project(tmp_path)
    (p / "bible").mkdir(exist_ok=True)
    (p / "bible" / "idea.md").write_text("без шапки\n", encoding="utf-8")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    problems = stage_gate(p, "script", "ep01")
    assert any("не читается" in x for x in problems), problems


def test_cast_gate_flags_card_without_canonical_appearance(tmp_path):
    """Одобренная карточка без блока canonical:appearance — промпт кадра нечем
    разворачивать; поймать надо гейтом, а не трейсбеком из build_jobs."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character",
          "рыжий кот, без канонического блока", status="approved")
    problems = stage_gate(p, "storyboard", "ep01")
    assert any("canonical:appearance" in x for x in problems), problems


def test_storyboard_gate_flags_style_guide_without_canonical_block(tmp_path):
    """Симметрия с персонажами: без canonical:style разворачивать {{style}} нечем,
    и expand_prompt упал бы уже на платной стадии."""
    p = make_project(tmp_path, episodes=1)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    write(p / "bible" / "style-guide.md", "style-guide", "стиль без блока",
          status="approved")
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    problems = stage_gate(p, "storyboard", "ep01")
    assert any("canonical:style" in x for x in problems), problems
