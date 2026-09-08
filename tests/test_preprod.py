"""Тесты состояния артефактов и гейтов пре-продакшна (спека 2026-08-02 §5)."""
import json
from pathlib import Path

import pytest

from factory.artifact import Artifact, body_sha, load_artifact, save_artifact
from factory.preprod import artifact_state, dependencies
from factory.preprod import (episode_ids, next_stage, stage_gate,
                             stage_problems, stale_reason)
from factory.project import ProjectError


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
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
    }), encoding="utf-8")
    return tmp_path


def test_episode_ids_from_project(tmp_path):
    p = make_project(tmp_path, episodes=3)
    assert episode_ids(p) == ["ep01", "ep02", "ep03"]


@pytest.mark.parametrize("bad", [0, -1, "три", None])
def test_episode_ids_rejects_nonsense(tmp_path, bad):
    """`episodes: 0` молча становился одной серией, отрицательное — пустым списком,
    из-за чего next_stage объявлял «всё закрыто» на пустом проекте."""
    p = make_project(tmp_path, episodes=bad)
    with pytest.raises(ProjectError, match="episodes"):
        episode_ids(p)


def test_stale_reason_names_the_culprit(tmp_path):
    """Спека §5 обосновывает отдельное состояние тем, что человек должен понять,
    ЧЕЙ файл перечитывать; сообщение сообщало только, что чужой."""
    p = make_project(tmp_path)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    idea_sha = load_artifact(p / "bible" / "idea.md").sha
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": idea_sha}])

    write(p / "bible" / "idea.md", "idea", "другая идея", status="approved")
    reason = stale_reason(p, p / "bible" / "season-arc.md")
    assert "bible/idea.md" in reason, reason

    (p / "bible" / "idea.md").unlink()
    assert "bible/idea.md" in stale_reason(p, p / "bible" / "season-arc.md")


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
    assert next_stage(p) == ("characters", "ep01"), "референс ещё не принят"
    _accept_ref(p, "Мурзик")
    assert next_stage(p) == ("storyboard", "ep01")

    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")
    assert next_stage(p) == ("script", "ep02")


def test_next_stage_returns_to_storyboard_on_unusable_plan(tmp_path):
    """Пустой shots.json — раскадровка НЕ сделана, а не «всё закрыто».

    Раньше резолвер смотрел только на существование файла и на `{}` отвечал
    «делать нечего»: непригодный план выглядел завершённой работой. Теперь план
    читается, и отказ загрузчика возвращает человека на тот этап, где он пишется.
    """
    p = make_project(tmp_path, episodes=1)
    for rel, kind in (("bible/idea.md", "idea"), ("bible/season-arc.md", "season-arc"),
                      ("bible/style-guide.md", "style-guide")):
        write(p / rel, kind, "текст", status="approved")
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")
    assert next_stage(p) == ("storyboard", "ep01")


# --- Находка ревью: персонаж, введённый в поздней серии, проходил гейт без карточки ---

def _accept_ref(p, name, card_sha=None):
    """Отметить референс персонажа принятым ревью — этап characters закрыт только
    когда закрыты обе его половины: тексты карточек и платные референсы.

    card_sha пишется так же, как это делает generate_batch при приёмке: без него
    правка карточки после приёмки не делает референс устаревшим (старые манифесты
    поля не имеют — их не блокируем задним числом)."""
    from factory.manifest import Manifest
    m = Manifest(p / "manifest.json")
    item_id = f"bible/characters/{name}"
    if item_id not in m.data["items"]:
        m.add(item_id, kind="character_ref")
        m.set_status(item_id, "generating")
        extra = {"card_sha": card_sha} if card_sha else {}
        m.set_status(item_id, "generated", **extra)
        m.set_status(item_id, "done")
    m.save()


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
    _accept_ref(p, "Мурзик")
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
    """Поправка D-3: одной одобренной карточки мало — раскадровка опирается ещё и
    на ПРИНЯТЫЙ референс, поэтому доводим этап characters до конца."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    _accept_ref(p, "Мурзик")
    assert stage_gate(p, "storyboard", "ep01") == []


def test_storyboard_gate_closed_while_ref_not_accepted(tmp_path):
    """D-3: гейт storyboard — один на всех потребителей (factory.py check,
    next_stage, платная стадия generate_batch). Пока референс персонажа не принят
    ревью, он закрыт: раньше про референсы знал только generate_batch, и три
    команды отвечали про одно состояние по-разному."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    problems = stage_gate(p, "storyboard", "ep01")
    assert any("референс" in x for x in problems), problems


def test_storyboard_gate_does_not_blame_ref_of_a_character_without_card(tmp_path):
    """У персонажа, чья карточка ещё не написана, «референс не генерировался» —
    следствие, а не отдельная проблема: две строки на одного персонажа увели бы
    человека генерировать референс по описанию, которого нет."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    problems = stage_gate(p, "storyboard", "ep01")
    assert any("Мурзик.md" in x for x in problems), problems
    assert not any("референс" in x for x in problems), problems


def test_characters_gate_ignores_unaccepted_ref(tmp_path):
    """Референс — вторая половина ЭТОГО этапа: требовать его на входе значило бы
    закрыть стадию, которая его и производит."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY, status="approved")
    assert stage_gate(p, "characters", "ep01") == []


def test_characters_gate_flags_stale_accepted_ref(tmp_path):
    """Принятый, но устаревший референс этап сам не починит: manifest.add
    идемпотентен, `done` в `pending` не возвращается — стадия молча отвечала бы
    «нечего делать» кодом 0, а резолвер звал бы её снова и снова."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    card = p / "bible" / "characters" / "Мурзик.md"
    art = write(card, "character", CHAR_BODY, status="approved")
    _accept_ref(p, "Мурзик", card_sha=art.sha)

    write(card, "character",
          "<!-- canonical:appearance -->СЕРЫЙ кот<!-- /canonical:appearance -->",
          status="approved")
    problems = stage_gate(p, "characters", "ep01")
    assert any("изменилась после приёмки" in x for x in problems), problems


def test_storyboard_gate_flags_card_changed_after_ref_accepted(tmp_path):
    """Правка внешности после приёмки референса делает картинку устаревшей.
    Проверка переехала из generate_batch в общий гейт (D-3) — значит её видит и
    factory.py check, а не только платная стадия."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    card = p / "bible" / "characters" / "Мурзик.md"
    art = write(card, "character", CHAR_BODY, status="approved")
    _accept_ref(p, "Мурзик", card_sha=art.sha)

    new_body = "<!-- canonical:appearance -->СЕРЫЙ кот<!-- /canonical:appearance -->"
    write(card, "character", new_body, status="approved")
    problems = stage_gate(p, "storyboard", "ep01")
    assert any("изменилась после приёмки" in x for x in problems), problems


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


def test_next_stage_stays_on_characters_until_refs_accepted(tmp_path):
    """Карточки одобрены, но референсы не сгенерированы — этап characters не закрыт.
    Иначе драйвер уходил бы в storyboard и упирался в код 3 на каждом эпизоде."""
    from factory.manifest import Manifest
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY,
          status="approved")
    assert next_stage(p) == ("characters", "ep01")

    m = Manifest(p / "manifest.json")
    m.add("bible/characters/Мурзик", kind="character_ref")
    for st in ("generating", "generated", "done"):
        m.set_status("bible/characters/Мурзик", st)
    m.save()
    assert next_stage(p) == ("storyboard", "ep01")


# --- Ревью 2026-08-02: внешние данные строили пути ---

def test_character_name_escaping_project_is_a_gate_problem(tmp_path):
    """Имя персонажа из frontmatter сценария напрямую становится путём карточки и
    файлом референса. '../../secret' читал и ПИСАЛ бы вне проекта."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["../../../secret"])
    problems = stage_gate(p, "characters", "ep01")
    assert any("не годится как имя файла" in x for x in problems), problems


@pytest.mark.parametrize("name", ["a/b", r"a\b", "..", ".", "", "/abs"])
def test_is_safe_name_rejects_path_pieces(name):
    from factory.preprod import is_safe_name
    assert not is_safe_name(name)


def test_is_safe_name_accepts_ordinary_names():
    from factory.preprod import is_safe_name
    assert is_safe_name("Мурзик") and is_safe_name("murzik-2")


def test_dependency_outside_project_is_stale_not_approved(tmp_path):
    """depends_on берётся из данных: путь наружу читался и хешировался, и артефакт
    объявлялся approved на основании файла вне проекта."""
    p = make_project(tmp_path, episodes=1)
    outside = tmp_path.parent / "чужое.md"
    write(outside, "idea", "чужое")
    body = "арка"
    write(p / "bible" / "season-arc.md", "season-arc", body, status="approved",
          depends_on=[{"path": "../../чужое.md", "sha": body_sha("чужое")}])
    assert artifact_state(p, p / "bible" / "season-arc.md") == "stale_deps"


def test_story_gate_rejects_broken_project_json(tmp_path):
    """Спека §5 требует для этапа story валидный project.json, но гейт не смотрел
    на него вовсе: битый бриф обнаруживался на generate_batch — уже после того,
    как написаны идея, арка и стайл-гайд."""
    p = make_project(tmp_path)
    (p / "project.json").write_text('{"name": "pilot"}', encoding="utf-8")
    problems = stage_gate(p, "story")
    assert problems, "гейт обязан отбить неполный project.json"
    assert any("project.json" in x for x in problems), problems


def _generated_ref(p, name):
    """Референс сгенерирован и ЖДЁТ ревью человека — машине здесь делать нечего."""
    from factory.manifest import Manifest
    m = Manifest(p / "manifest.json")
    item_id = f"bible/characters/{name}"
    m.add(item_id, kind="character_ref")
    m.set_status(item_id, "generating")
    m.set_status(item_id, "generated")
    m.save()


def test_next_stage_does_not_freeze_season_on_ref_awaiting_review(tmp_path):
    """D-7 первого живого прогона: резолвер не отдавал ничего из ep02, пока у ep01
    не принят референс. Референс на ревью ждёт ЧЕЛОВЕКА, а вся текстовая работа
    ep02 бесплатна и от ep01 не зависит — замораживать сезон незачем."""
    p = make_project(tmp_path, episodes=2)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved",
          characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY,
          status="approved")
    _generated_ref(p, "Мурзик")

    assert next_stage(p) == ("script", "ep02"), \
        "ep01 ждёт человека — сценарий ep02 писать можно уже сейчас"


def test_next_stage_returns_to_waiting_episode_when_nothing_else_left(tmp_path):
    """Пропуск — не забывание: когда актуальной работы больше нет, резолвер обязан
    вернуться к серии, которая ждёт ревью, а не сказать «всё закрыто»."""
    p = make_project(tmp_path, episodes=2)
    _closed_story(p)
    for ep in ("ep01", "ep02"):
        write(p / "episodes" / ep / "script.md", "script", "с", status="approved",
              characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY,
          status="approved")
    _generated_ref(p, "Мурзик")
    assert next_stage(p) == ("characters", "ep01")


def test_next_stage_does_not_skip_episode_the_driver_can_still_act_on(tmp_path):
    """Пропускается только ожидание человека. Референс, который ещё не
    генерировался, — работа для машины, и перескакивать через неё нельзя:
    иначе платная половина этапа никогда бы не звалась (находка финального ревью
    прошлой ветки, повторять её нельзя)."""
    p = make_project(tmp_path, episodes=2)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved",
          characters=["Мурзик"])
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY,
          status="approved")
    assert next_stage(p) == ("characters", "ep01")


# --- U-11: stage_problems делит stage_gate на блокеры и работу самого этапа ---

def test_characters_own_work_names_unwritten_card(tmp_path):
    """Карточка персонажа ещё не написана — это работа самого этапа characters,
    а не блокер: «Мурзик.md не существует» означает «садись и пиши», а не «стоп»
    (находка U-11 первого живого прогона)."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    blockers, own_work = stage_problems(p, "characters", "ep01")
    assert blockers == []
    assert any("Мурзик" in x for x in own_work), own_work


def test_characters_blockers_include_unapproved_script(tmp_path):
    """Сценарий не одобрен — чужой вход этапа characters, настоящий блокер. Та же
    фикстура объявляет состав (Мурзик), поэтому характерным образом порождает и
    own_work — это тоже нужно проверить, а не только blockers."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          characters=["Мурзик"])  # status по умолчанию draft
    blockers, own_work = stage_problems(p, "characters", "ep01")
    assert any("script.md" in x for x in blockers), blockers
    assert any("Мурзик" in x for x in own_work), own_work


def test_characters_unsafe_name_is_a_blocker_not_own_work(tmp_path):
    """Небезопасное имя в составе серии чинится правкой уже одобренного
    episodes/<ep>/script.md — артефакта ПРЕДЫДУЩЕГО этапа, а не карточки,
    которую пишет сам characters. Значит это настоящий блокер, а не своя
    работа этапа: иначе check отвечал бы кодом 0 «этап можно вести» на
    состояние, которое сам этап разрешить не может — зеркало обмана U-11
    (находка ревью)."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["../../../secret"])
    blockers, own_work = stage_problems(p, "characters", "ep01")
    assert any("не годится как имя файла" in x for x in blockers), blockers
    assert not any("не годится как имя файла" in x for x in own_work), own_work


def test_storyboard_has_no_own_work(tmp_path):
    """Раскадровка не производит ни карточек, ни референсов — это выход
    ПРЕДЫДУЩЕГО этапа, то есть целиком чужой вход: own_work пуст, всё — блокеры."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    blockers, own_work = stage_problems(p, "storyboard", "ep01")
    assert own_work == []
    assert any("Мурзик" in x for x in blockers), blockers


def test_stage_gate_is_blockers_plus_own_work(tmp_path):
    """Инвариант: контракт платной стадии не менялся. generate_batch и next_stage
    зовут stage_gate напрямую и получают ПОЛНЫЙ список — деление на две категории
    существует только для factory.py check."""
    p = make_project(tmp_path, episodes=1)
    _closed_story(p)
    write(p / "episodes" / "ep01" / "script.md", "script", "с1",
          status="approved", characters=["Мурзик"])
    for stage in ("story", "script", "characters", "storyboard"):
        blockers, own_work = stage_problems(p, stage, "ep01")
        assert sorted(stage_gate(p, stage, "ep01")) == sorted(blockers + own_work)


def test_stage_problems_bad_project_json_is_all_blockers(tmp_path):
    """Непригодный project.json — блокер, возвращается сразу, own_work пустой."""
    (tmp_path / "bible").mkdir()
    (tmp_path / "project.json").write_text('{"name": "pilot"}', encoding="utf-8")
    blockers, own_work = stage_problems(tmp_path, "characters", "ep01")
    assert own_work == []
    assert blockers, "непригодный project.json обязан быть блокером"


def test_stage_problems_unknown_stage_is_all_blockers(tmp_path):
    """Неизвестный этап — блокер, own_work пустой."""
    p = make_project(tmp_path, episodes=1)
    blockers, own_work = stage_problems(p, "nope", "ep01")
    assert own_work == []
    assert blockers


# --- платная половина в резолвере шагов (дизайн 2026-09-04) ---

from factory.manifest import Manifest  # noqa: E402


def _ready_project(tmp_path, shots, audio=None):
    """Проект, у которого бесплатная половина закрыта, и есть план съёмки."""
    p = make_project(tmp_path, episodes=1)
    for rel, kind in (("bible/idea.md", "idea"), ("bible/season-arc.md", "season-arc"),
                      ("bible/style-guide.md", "style-guide")):
        write(p / rel, kind, "текст", status="approved")
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    write(p / "bible" / "characters" / "Мурзик.md", "character", CHAR_BODY,
          status="approved")
    _accept_ref(p, "Мурзик")
    ep = p / "episodes" / "ep01"
    ep.mkdir(parents=True, exist_ok=True)
    (ep / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    if audio is not None:
        (ep / "audio.json").write_text(json.dumps(audio), encoding="utf-8")
    return p


def _done(manifest, item_id, kind):
    manifest.add(item_id, kind=kind)
    manifest.set_status(item_id, "generating")
    manifest.set_status(item_id, "generated")
    manifest.set_status(item_id, "done")


SHOTS_1 = {"episode": "ep01",
           "frames": [{"n": 1, "prompt": "a"}],
           "segments": [{"n": 1, "start_frame": 1, "prompt": "m"}]}


def test_next_stage_reaches_paid_half(tmp_path):
    """После раскадровки резолвер обязан вести дальше: кадры, отрезки, монтаж.

    Пока он останавливался на storyboard, автономный драйвер до звука не доходил
    никогда — половина конвейера была недостижима командой `factory.py next`.
    """
    p = _ready_project(tmp_path, SHOTS_1)
    assert next_stage(p) == ("storyboard_generate", "ep01")


def test_next_stage_segments_after_frames_accepted(tmp_path):
    p = _ready_project(tmp_path, SHOTS_1)
    m = Manifest(p / "manifest.json")
    _done(m, "ep01/storyboard/001", "frame")
    m.save()
    assert next_stage(p) == ("segments", "ep01")


def test_next_stage_render_when_everything_accepted(tmp_path):
    p = _ready_project(tmp_path, SHOTS_1)
    m = Manifest(p / "manifest.json")
    _done(m, "ep01/storyboard/001", "frame")
    _done(m, "ep01/segments/001", "segment")
    m.save()
    assert next_stage(p) == ("render", "ep01")


def test_next_stage_audio_before_render_when_plan_exists(tmp_path):
    audio = {"voice_lines": [{"id": "v1", "speaker": "a", "voice": "Kore",
                              "text": "x", "segment": 1, "offset": 0}]}
    p = _ready_project(tmp_path, SHOTS_1, audio)
    m = Manifest(p / "manifest.json")
    _done(m, "ep01/storyboard/001", "frame")
    _done(m, "ep01/segments/001", "segment")
    m.save()
    assert next_stage(p) == ("audio", "ep01")


def test_next_stage_none_when_episode_is_rendered(tmp_path):
    # Действительно закрытая серия: кадры и отрезки приняты, готовый файл лежит.
    p = _ready_project(tmp_path, SHOTS_1)
    m = Manifest(p / "manifest.json")
    _done(m, "ep01/storyboard/001", "frame")
    _done(m, "ep01/segments/001", "segment")
    m.save()
    final = p / "episodes" / "ep01" / "final"
    final.mkdir(parents=True, exist_ok=True)
    (final / "ep01.mp4").write_bytes(b"stub")
    assert next_stage(p) is None


def test_next_stage_waits_for_human_on_generated_frames(tmp_path):
    # Кадры сгенерированы и ждут приёмки: машине делать нечего, но и отрезки
    # запускать нельзя — они строятся на ПРИНЯТЫХ кадрах.
    p = _ready_project(tmp_path, SHOTS_1)
    m = Manifest(p / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated")
    m.save()
    assert next_stage(p) is None


def test_next_stage_waits_for_human_on_generated_segments(tmp_path):
    """Отрезки сгенерированы, но не приняты — машине делать нечего.

    Ревью 2026-09-05: `_pending` считал `generated` сделанным, и резолвер
    проваливался дальше к монтажу. Но монтаж требует ПРИНЯТЫХ отрезков и
    отказывает кодом 3 — то есть `next` называл стадию, которую её собственный
    гейт на этом же состоянии отбивает. Ровно то расхождение «одно состояние,
    разные ответы», ради которого у кадров уже есть отдельная проверка.
    """
    p = _ready_project(tmp_path, SHOTS_1)
    m = Manifest(p / "manifest.json")
    _done(m, "ep01/storyboard/001", "frame")
    m.add("ep01/segments/001", kind="segment")
    m.set_status("ep01/segments/001", "generating")
    m.set_status("ep01/segments/001", "generated")
    m.save()
    assert next_stage(p) is None


# --- жанр решает, какие стадии существуют ---------------------------------

GENRE_KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


def _educational(tmp_path):
    """Проект познавательного жанра: диктор вместо персонажей."""
    proj = tmp_path / "проект"
    (proj / "bible").mkdir(parents=True)
    (proj / "episodes" / "ep01").mkdir(parents=True)
    (proj / "project.json").write_text(json.dumps({
        "name": "проект", "type": "series", "genre": "educational",
        "theme": "почему небо синее", "episodes": 1, "episode_duration_sec": 60,
        "models": {"image": {"model": "z_image_turbo"},
                   "video": {"model": "vidu_q2_turbo"}},
    }, ensure_ascii=False), encoding="utf-8")
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md",
                "episodes/ep01/script.md"):
        # content_sha обязан совпадать с телом, иначе артефакт числится
        # stale_self и гейт честно возвращает более раннюю стадию.
        art = Artifact(path=proj / rel, meta={"status": "approved"}, body="текст")
        art.meta["content_sha"] = art.sha
        save_artifact(art)
    return proj


def test_next_stage_skips_characters_for_educational(tmp_path):
    """У познавательного нет персонажей — стадии про них не существует."""
    proj = _educational(tmp_path)
    stage, _ = next_stage(proj)
    assert stage == "storyboard", "characters не должен появляться у этого жанра"


def test_stage_problems_rejects_stage_absent_in_genre(tmp_path):
    proj = _educational(tmp_path)
    blockers, _own = stage_problems(proj, "characters", "ep01")
    assert any("educational" in b for b in blockers), blockers


def test_lipsync_blocked_where_genre_forbids_it(tmp_path):
    """Губ в кадре нет: стадия недоступна до всякой сметы."""
    proj = _educational(tmp_path)
    blockers, _own = stage_problems(proj, "lipsync", "ep01")
    assert blockers, "липсинк обязан быть закрыт у жанра без персонажей"


def test_narrative_genre_keeps_characters(tmp_path):
    """Тот же проект в повествовательном жанре обязан пройти через персонажей."""
    proj = _educational(tmp_path)
    data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    data["genre"] = "animation"
    (proj / "project.json").write_text(json.dumps(data, ensure_ascii=False),
                                       encoding="utf-8")
    # Состав объявляется полем characters во frontmatter сценария: без него
    # у этапа characters нет работы, и конвейер законно уходит дальше.
    art = Artifact(path=proj / "episodes/ep01/script.md",
                   meta={"status": "approved", "characters": ["Устинья"]}, body="текст")
    art.meta["content_sha"] = art.sha
    save_artifact(art)

    stage, _ = next_stage(proj)
    assert stage == "characters"
