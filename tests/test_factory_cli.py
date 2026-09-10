"""Тесты CLI пре-продакшна (спека 2026-08-02 §6)."""
import json
import subprocess

import pytest

import factory_cli_entry as fc
from factory import preprod  # см. шаг 3: тонкая обёртка над scripts/factory.py
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
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
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


def _approved(path, kind, body, **extra):
    """Одобренный артефакт с корректным content_sha (иначе artifact_state
    справедливо считает его изменённым после одобрения)."""
    from factory.artifact import body_sha
    save_artifact(Artifact(path=path,
                           meta={"kind": kind, "status": "approved",
                                 "content_sha": body_sha(body), **extra},
                           body=body))


def _project_ready_for_storyboard(proj):
    """Всё текстовое одобрено, состав серии объявлен, карточка персонажа готова.
    Не сделано ровно одно: референс персонажа не сгенерирован и не принят ревью."""
    _approved(proj / "bible" / "idea.md", "idea", "идея")
    _approved(proj / "bible" / "season-arc.md", "season-arc", "арка")
    _approved(proj / "bible" / "style-guide.md", "style-guide",
              "<!-- canonical:style -->flat 2D<!-- /canonical:style -->")
    _approved(proj / "episodes" / "ep01" / "script.md", "script", "с1",
              characters=["Мурзик"])
    _approved(proj / "bible" / "characters" / "Мурзик.md", "character",
              "<!-- canonical:appearance -->рыжий кот<!-- /canonical:appearance -->")


def test_check_storyboard_closed_while_ref_not_accepted(proj, capsys):
    """D-3: три команды давали три ответа про одно состояние — `check` говорил
    «гейт открыт», `next` вёл обратно на characters, а платная стадия
    отказывала. Команда, чей единственный смысл — ответить «можно ли запускать
    этап», обязана учитывать принятость референсов, как и generate_batch."""
    _project_ready_for_storyboard(proj)
    assert run("check", "--project", proj, "--stage", "storyboard",
               "--episode", "ep01") == 3
    out = capsys.readouterr().out
    assert "гейт открыт" not in out
    assert "референс" in out


def test_check_storyboard_opens_after_ref_accepted(proj):
    """Обратная сторона D-3: принятый ревью референс открывает гейт — проверка
    отбивает непринятый референс, а не запрещает раскадровку вообще."""
    from factory.manifest import Manifest
    _project_ready_for_storyboard(proj)
    m = Manifest(proj / "manifest.json")
    m.add("bible/characters/Мурзик", kind="character_ref")
    for st in ("generating", "generated", "done"):
        m.set_status("bible/characters/Мурзик", st)
    m.save()
    assert run("check", "--project", proj, "--stage", "storyboard",
               "--episode", "ep01") == 0


def test_check_characters_reports_unwritten_cards_as_own_work_not_blocker(proj, capsys):
    """U-11: карточку персонажа этап characters производит сам — «не существует»
    здесь значит «садись и пиши», а не «стоп». Код 0, в выводе есть имя
    персонажа и упоминание платной половины, и НЕТ «запускать нельзя»."""
    _approved(proj / "bible" / "idea.md", "idea", "идея")
    _approved(proj / "bible" / "season-arc.md", "season-arc", "арка")
    _approved(proj / "episodes" / "ep01" / "script.md", "script", "с1",
              characters=["Мурзик"])
    assert run("check", "--project", proj, "--stage", "characters",
               "--episode", "ep01") == 0
    out = capsys.readouterr().out
    assert "Мурзик" in out
    assert "запускать нельзя" not in out
    assert "платная половина" in out


def test_check_characters_returns_3_for_unsafe_name(proj, capsys):
    """Небезопасное имя в составе серии — блокер, а не работа этапа characters
    (находка ревью U-11, зеркало исходной находки): чинится правкой уже
    одобренного episodes/<ep>/script.md, артефакта ПРЕДЫДУЩЕГО этапа, а не
    карточкой, которую пишет сам characters."""
    _approved(proj / "bible" / "idea.md", "idea", "идея")
    _approved(proj / "bible" / "season-arc.md", "season-arc", "арка")
    _approved(proj / "episodes" / "ep01" / "script.md", "script", "с1",
              characters=["../../../secret"])
    assert run("check", "--project", proj, "--stage", "characters",
               "--episode", "ep01") == 3
    out = capsys.readouterr().out
    assert "ГЕЙТ ЗАКРЫТ" in out
    assert "не годится как имя файла" in out


def test_check_characters_returns_3_when_script_not_approved(proj, capsys):
    """Сценарий — чужой вход этапа characters, а не его работа: пока он не
    одобрен, гейт закрыт по-настоящему, код 3. Состав объявлен в том же
    сценарии, поэтому own_work тоже не пуст — код 3 обязан печатать и его,
    с префиксом `(работа самого этапа)`, чтобы человек видел разницу (Minor 2
    ревью U-11: без объявленного состава эта ветка cmd_check не исполнялась
    ни одним тестом)."""
    save_artifact(Artifact(path=proj / "episodes" / "ep01" / "script.md",
                           meta={"kind": "script", "status": "draft",
                                 "characters": ["Мурзик"]},
                           body="с1"))
    assert run("check", "--project", proj, "--stage", "characters",
               "--episode", "ep01") == 3
    out = capsys.readouterr().out
    assert "(работа самого этапа)" in out


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


def test_feedback_defaults_to_none(proj):
    run("init", "--project", proj)
    from factory.preprod import feedback_state
    assert feedback_state(proj / "bible" / "idea.md") == "none"


def test_status_shows_feedback_column(proj, capsys):
    run("init", "--project", proj)
    run("status", "--project", proj)
    out = capsys.readouterr().out
    assert "feedback" in out
    assert "none" in out


def test_feedback_set_records_state(proj):
    run("init", "--project", proj)
    assert run("feedback", "--project", proj, "bible/idea.md", "--state", "recorded") == 0
    from factory.preprod import feedback_state
    assert feedback_state(proj / "bible" / "idea.md") == "recorded"


def test_feedback_rejects_unknown_state(proj):
    run("init", "--project", proj)
    assert run("feedback", "--project", proj, "bible/idea.md", "--state", "great") == 1


def test_feedback_survives_broken_artifact(proj, capsys):
    """`approve` и `status` битый артефакт обрабатывают, а `feedback` падал
    трейсбеком — асимметрия внутри одного CLI."""
    run("init", "--project", proj)
    (proj / "bible" / "idea.md").write_text("нет никакого frontmatter",
                                            encoding="utf-8")
    assert run("feedback", "--project", proj, "bible/idea.md",
               "--state", "recorded") == 1
    assert "не читается" in capsys.readouterr().out


def test_diff_reports_no_baseline_when_never_committed(proj, capsys):
    run("init", "--project", proj)
    assert run("diff", "--project", proj, "bible/idea.md") == 0
    assert "нет базовой версии" in capsys.readouterr().out


def test_budget_allows_estimate_within_remainder(proj):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
        "autonomy": "full", "budget_usd": 10,
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "3.0") == 0


def test_budget_blocks_estimate_over_remainder(proj, capsys):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
        "autonomy": "full", "budget_usd": 1,
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "3.0") == 3
    # Регистр сравниваем без учёта регистра: репо стабильно использует ЗАГЛАВНЫЕ
    # буквы для тревожных сообщений (ГЕЙТ ЗАКРЫТ, ЛИМИТ ОТКЛОНЕНИЙ ИСЧЕРПАН —
    # scripts/factory.py, scripts/generate_batch.py), а не то, что дал брифовый
    # эталон дословно; смысл проверки — что сообщение вообще упоминает бюджет.
    assert "бюджет" in capsys.readouterr().out.lower()


def test_budget_counts_already_spent(proj):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
        "autonomy": "full", "budget_usd": 5,
    }), encoding="utf-8")
    from factory.manifest import Manifest
    m = Manifest(proj / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    # Манифест разрешает только pending -> generating -> generated (factory/manifest.py
    # ALLOWED); брифовый эталон прыгал прямо в generated и падал ManifestError.
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated", credits_spent=4.5)
    m.save()
    assert run("budget", "--project", proj, "--estimate", "1.0") == 3


def test_budget_ceiling_prints_four_decimals(proj, capsys):
    """D-6, тот же дефект в cmd_budget, что уже чинили в generate_batch.py:130 —
    потолок печатается с тем же числом знаков после запятой (четыре), что смета
    и остаток на той же строке. При budget_usd: 0.002 двузначный потолок выглядел
    бы нулевым (потолок 0.00)."""
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
        "autonomy": "full", "budget_usd": 0.002,
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "1.5") == 3
    assert "потолок $0.0020" in capsys.readouterr().out


def test_budget_without_a_ceiling_is_not_a_refusal(proj, capsys):
    """Потолок перестал быть обязательным автономному режиму (2026-09-09).

    Тормозом стала смета всего прогона с подтверждением перед стартом, а
    требование выдумать число мешало включить режим вовсе.
    """
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10, "autonomy": "full",
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "0.1") == 0
    assert "не задан" in capsys.readouterr().out


def test_budget_ceiling_applies_in_manual_mode_too(proj, capsys):
    """Заданный потолок работает всегда: он затем и задан."""
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10, "budget_usd": 1,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "3.0") == 3
    assert "БЮДЖЕТ ИСЧЕРПАН" in capsys.readouterr().out


def test_effective_feedback_reports_pending_after_human_edit(proj, monkeypatch):
    """feedback: none + файл правлен после коммита = pending. Без этой поправки
    /factory-feedback не нашёл бы ни одной строки и петля §11 была бы мёртвой."""
    import factory_cli_entry as fce
    run("init", "--project", proj)
    path = proj / "bible" / "idea.md"

    monkeypatch.setattr(preprod, "_edited_since_commit", lambda p: False)
    assert preprod.effective_feedback(path) == "none"

    monkeypatch.setattr(preprod, "_edited_since_commit", lambda p: True)
    assert preprod.effective_feedback(path) == "pending"


def test_effective_feedback_keeps_recorded_over_edit(proj, monkeypatch):
    """Уже разобранная правка не откатывается в pending при каждом чихе."""
    import factory_cli_entry as fce
    run("init", "--project", proj)
    run("feedback", "--project", proj, "bible/idea.md", "--state", "recorded")
    monkeypatch.setattr(preprod, "_edited_since_commit", lambda p: True)
    assert preprod.effective_feedback(proj / "bible" / "idea.md") == "recorded"


@pytest.fixture
def git_repo(proj):
    """`proj` поверх настоящего git-репозитория (корень — родительский tmp_path).

    D-1 проверяет, что _edited_since_commit реально понимает разницу между HEAD и
    рабочей копией через `git show`/`git rev-parse` — монки в двух тестах выше не
    годятся, они подменяют саму функцию. Другой git-фикстуры в tests/ нет (проверено
    по conftest.py и остальным test_*.py), поэтому заводим её здесь же, рядом с
    тестами effective_feedback.
    """
    root = proj.parent.parent
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root,
                   check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    return proj


def _commit_all(proj, message="commit"):
    root = proj.parent.parent
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


def test_effective_feedback_stays_none_after_approve_rewrites_frontmatter(git_repo):
    """D-1: `approve` переписывает frontmatter (status/approved_at/content_sha) и
    не коммитит, но тело не трогает. До починки это читалось как правка человека —
    ложный сигнал: /factory-feedback разбирал бы «правки», которых не было, на
    каждом одобрении в проекте."""
    proj = git_repo
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    _commit_all(proj)

    assert run("approve", "--project", proj, "bible/idea.md") == 0
    assert preprod.effective_feedback(proj / "bible" / "idea.md") == "none"


def test_effective_feedback_still_pending_when_body_edited_after_commit(git_repo):
    """Регресс-защита к D-1: настоящая правка ТЕЛА человеком после коммита обязана
    по-прежнему давать pending. «pending недостижим» уже был находкой ревью один
    раз (и `_edited_since_commit` появился как починка) — правка D-1 не должна
    воскресить ту же дыру с другой стороны."""
    proj = git_repo
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    _commit_all(proj)

    art = load_artifact(proj / "bible" / "idea.md")
    art.body = "идея, переписанная человеком"
    save_artifact(art)

    assert preprod.effective_feedback(proj / "bible" / "idea.md") == "pending"


def test_edited_since_commit_false_for_new_uncommitted_file(git_repo):
    """D-1 краевой случай из брифа: артефакт создан, но ещё ни разу не коммитился —
    `git show HEAD:<путь>` не находит его в HEAD. _edited_since_commit обязана
    вернуть False («не правлен»), а не упасть: cmd_status зовёт эту функцию на
    КАЖДОМ артефакте проекта (scripts/factory.py:117-122), и необработанное
    исключение здесь роняет всю команду status, а не одну строку."""
    proj = git_repo
    _commit_all(proj, "initial")  # коммитим project.json — HEAD существует
    run("init", "--project", proj)  # создаёт артефакты, но НЕ коммитит их
    path = proj / "bible" / "idea.md"

    assert preprod._edited_since_commit(path) is False
    assert run("status", "--project", proj) == 0


def test_edited_since_commit_false_outside_git_repo(proj):
    """D-1 краевой случай из брифа: вне git-репозитория (`proj` без фикстуры
    `git_repo` — `git init` тут не вызывался) `git rev-parse --show-toplevel`
    отдаёт ненулевой код. _edited_since_commit обязана вернуть False, а не
    упасть, и cmd_status обязан по-прежнему отработать без исключения."""
    run("init", "--project", proj)
    path = proj / "bible" / "idea.md"

    assert preprod._edited_since_commit(path) is False
    assert run("status", "--project", proj) == 0


def test_edited_since_commit_false_when_head_version_unparseable(git_repo):
    """D-1 краевой случай из брифа: версия артефакта в самом HEAD битая (frontmatter
    испорчен ещё в коммите) — split_frontmatter кидает ArtifactError на тексте из
    `git show`. _edited_since_commit обязана перехватить это и вернуть False, а не
    уронить cmd_status на первом же битом коммите в истории проекта."""
    proj = git_repo
    run("init", "--project", proj)
    path = proj / "bible" / "idea.md"
    path.write_text("это не YAML-frontmatter вообще", encoding="utf-8")
    _commit_all(proj)
    # Рабочая копия снова валидна (человек её не трогал) — битая только версия в
    # HEAD, чтобы тест бил именно в ветку разбора HEAD, а не в симметричную ветку
    # для рабочей копии.
    save_artifact(Artifact(path=path, meta={"kind": "idea", "status": "draft"},
                           body="идея"))

    assert preprod._edited_since_commit(path) is False
    assert run("status", "--project", proj) == 0


def test_approve_auto_marks_the_artifact(proj):
    """Спека §7: при auto_approve/full по файлу должно быть видно, что чекпоинт
    не смотрел человек. Иначе в режиме full по проекту не понять, одобрял ли его
    вообще кто-нибудь живой."""
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    assert run("approve", "--project", proj, "bible/idea.md", "--auto") == 0
    assert load_artifact(proj / "bible" / "idea.md").meta["approved_by"] == "auto"


def test_approve_without_auto_leaves_no_machine_mark(proj):
    run("init", "--project", proj)
    _write_body(proj / "bible" / "idea.md", "идея")
    assert run("approve", "--project", proj, "bible/idea.md") == 0
    assert "approved_by" not in load_artifact(proj / "bible" / "idea.md").meta


def test_cli_reports_broken_project_json_readably(proj, capsys):
    """Регресс, найденный финальным ревью ветки: после того как episode_ids начал
    поднимать ProjectError вместо тихой единицы, `init` на битом брифе стал падать
    трейсбеком — ровно тот класс дефекта (D-4), который эта же ветка чинила в
    generate_batch. Команду запускает человек: отказ с объяснением, не трейсбек."""
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 0, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
    }), encoding="utf-8")
    assert run("init", "--project", proj) == 1
    out = capsys.readouterr().out
    assert "episodes" in out and "Traceback" not in out, out


# --- выбор модели пользователем (дизайн 2026-09-04 §7) ---

VERIFIED_IMAGE = """---
id: z_image
type: image
status: verified
providers:
  wavespeed: { id: "w/z", usd_per_image: 0.005 }
---
# z
"""

SKELETON_IMAGE = """---
id: raw_model
type: image
status: skeleton
providers:
  wavespeed: { id: "x/y", usd_per_image: 0.01 }
---
# raw
"""


def _cards(tmp_path):
    kdir = tmp_path / "knowledge" / "images"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "z_image.md").write_text(VERIFIED_IMAGE, encoding="utf-8")
    (kdir / "raw_model.md").write_text(SKELETON_IMAGE, encoding="utf-8")


def test_models_lists_available_with_prices(proj, tmp_path, capsys):
    _cards(tmp_path)
    assert run("models", "--project", proj) == 0
    out = capsys.readouterr().out
    assert "image" in out and "video" in out
    assert "z_image" in out and "$" in out
    # скелет виден, но помечен как недоступный для трат
    assert "raw_model" in out and "skeleton" in out


def test_models_set_writes_choice_into_project(proj, tmp_path, capsys):
    _cards(tmp_path)
    assert run("models", "--project", proj, "--set", "image=z_image") == 0
    data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    assert data["models"]["image"]["model"] == "z_image"


def test_models_set_rejects_unverified_card(proj, tmp_path, capsys):
    # Карточка-скелет не должна становиться выбором: гейт трат отобьёт её позже,
    # но человек узнает об этом только на платной стадии.
    _cards(tmp_path)
    assert run("models", "--project", proj, "--set", "image=raw_model") == 1
    assert "skeleton" in capsys.readouterr().out


def test_models_set_rejects_unknown_role(proj, tmp_path, capsys):
    _cards(tmp_path)
    assert run("models", "--project", proj, "--set", "smell=z_image") == 1
    assert "smell" in capsys.readouterr().out


# --- сводная смета эпизода (дизайн 2026-09-04 §6) ---

def _estimate_project(tmp_path, proj):
    """Карточки и план съёмки, достаточные для сметы всего эпизода."""
    _cards(tmp_path)
    vdir = tmp_path / "knowledge" / "video"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "seedance_2_0.md").write_text("""---
id: seedance_2_0
type: video
status: verified
providers:
  wavespeed:
    supports_start_end: true
    pricing: flat
    tiers: { fast: { id: "w/s", usd_per_sec: 0.10 } }
    default_tier: fast
---
# s
""", encoding="utf-8")
    ep = proj / "episodes" / "ep01"
    ep.mkdir(parents=True, exist_ok=True)
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}],
        "segments": [{"n": 1, "start_frame": 1, "prompt": "m"},
                     {"n": 2, "start_frame": 2, "prompt": "m"}],
    }), encoding="utf-8")


def test_estimate_sums_stages(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    assert run("estimate", "--project", proj, "--episode", "ep01") == 0
    out = capsys.readouterr().out
    # 2 кадра по $0.005 + 2 отрезка по 5с × $0.10 = $0.01 + $1.00
    assert "storyboard" in out and "segments" in out
    assert "1.01" in out


def test_estimate_skips_already_accepted(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    from factory.manifest import Manifest
    m = Manifest(proj / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated")
    m.set_status("ep01/storyboard/001", "done")
    m.save()
    assert run("estimate", "--project", proj, "--episode", "ep01") == 0
    out = capsys.readouterr().out
    # один кадр уже принят — в смете остаётся один
    assert "1.005" in out


def test_estimate_reports_missing_shots(proj, tmp_path, capsys):
    _cards(tmp_path)
    assert run("estimate", "--project", proj, "--episode", "ep01") == 1
    assert "shots.json" in capsys.readouterr().out


def test_estimate_counts_audio_and_lipsync(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    adir = tmp_path / "knowledge" / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "tts_a.md").write_text("""---
id: tts_a
type: audio
audio_kind: tts
status: verified
providers:
  wavespeed: { id: "v/t", usd_per_image: 0.02, fields: { text: text } }
---
# t
""", encoding="utf-8")
    (adir / "lip_a.md").write_text("""---
id: lip_a
type: audio
audio_kind: lipsync
status: verified
providers:
  wavespeed: { id: "v/l", usd_per_image: 0.075, fields: { video: video } }
---
# l
""", encoding="utf-8")
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["audio"] = {"tts": {"model": "tts_a", "provider": "wavespeed"},
                             "lipsync": {"model": "lip_a", "provider": "wavespeed"}}
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    (proj / "episodes" / "ep01" / "audio.json").write_text(json.dumps({
        "voice_lines": [{"id": "v1", "speaker": "a", "voice": "Kore", "text": "x",
                         "segment": 1, "offset": 0, "lipsync": True}],
    }), encoding="utf-8")
    assert run("estimate", "--project", proj, "--episode", "ep01") == 0
    out = capsys.readouterr().out
    assert "voice_lines" in out and "lipsync" in out
    # 2 кадра $0.01 + 2 отрезка $1.00 + реплика $0.02 + липсинк $0.075
    assert "1.105" in out


def test_estimate_reports_budget_remainder(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["budget_usd"] = 5.0
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    assert run("estimate", "--project", proj, "--episode", "ep01") == 0
    out = capsys.readouterr().out
    assert "останется" in out and "3.99" in out


# --- check знает и платные стадии (дизайн 2026-09-04) ---

def test_check_knows_paid_stages(proj, tmp_path, capsys):
    """`check --stage segments` не должен отвечать «неизвестный этап».

    Половина конвейера — платная, и человек спрашивает про неё той же командой.
    Пока она знала только пре-продакшн, ответ «известны research…storyboard»
    выглядел так, будто отрезков в конвейере нет вовсе.
    """
    _estimate_project(tmp_path, proj)
    code = run("check", "--project", proj, "--stage", "segments", "--episode", "ep01")
    out = capsys.readouterr().out
    assert "неизвестный этап" not in out
    assert code in (0, 3)


def test_check_segments_blocked_until_frames_accepted(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    assert run("check", "--project", proj, "--stage", "segments",
               "--episode", "ep01") == 3
    assert "кадр" in capsys.readouterr().out.lower()


def test_check_still_rejects_truly_unknown_stage(proj, tmp_path, capsys):
    _estimate_project(tmp_path, proj)
    assert run("check", "--project", proj, "--stage", "smell",
               "--episode", "ep01") == 3
    assert "неизвестный этап" in capsys.readouterr().out


def test_models_shows_free_model_as_zero_not_missing(proj, tmp_path, capsys):
    # Цена 0 — валидная цена. Через `or` она проваливалась бы в следующее поле и
    # бесплатная модель показывалась бы как «цены нет».
    _cards(tmp_path)
    (tmp_path / "knowledge" / "images" / "free.md").write_text("""---
id: free_model
type: image
status: verified
providers:
  wavespeed: { id: "w/f", usd_per_image: 0 }
---
# free
""", encoding="utf-8")
    assert run("models", "--project", proj) == 0
    out = capsys.readouterr().out
    assert "free_model" in out
    assert "цены нет" not in out.split("free_model")[1].split("\n")[0]


def test_estimate_uses_duration_for_per_second_audio(proj, tmp_path, capsys):
    """Смета обязана учитывать ДЛИТЕЛЬНОСТЬ звука, а не только число единиц.

    Живой прогон 2026-09-05: эффекты и музыка тарифицируются посекундно, а смета
    считала их поштучно и промахнулась впятеро — $0.19 против $1.04 списанных.
    """
    _estimate_project(tmp_path, proj)
    adir = tmp_path / "knowledge" / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    (adir / "sfx_sec.md").write_text("""---
id: sfx_sec
type: audio
audio_kind: sfx
status: verified
providers:
  wavespeed: { id: "v/s", pricing: flat, usd_per_sec: 0.01, fields: { prompt: text_prompt, duration: duration } }
---
# sfx
""", encoding="utf-8")
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["audio"] = {"sfx": {"model": "sfx_sec", "provider": "wavespeed"}}
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    (proj / "episodes" / "ep01" / "audio.json").write_text(json.dumps({
        "sfx": [{"id": "s1", "prompt": "sea", "duration": 60, "segment": 1, "offset": 0},
                {"id": "s2", "prompt": "horn", "duration": 5, "segment": 1, "offset": 1}],
    }), encoding="utf-8")
    assert run("estimate", "--project", proj, "--episode", "ep01") == 0
    out = capsys.readouterr().out
    # 65 секунд по $0.01 = $0.65, а не две штуки по цене одной секунды
    assert "0.65" in out


# --- выбор модели текста берётся из брифа (2026-09-10) ---------------------

def test_text_stage_reads_model_and_effort_from_the_brief(proj, monkeypatch, capsys):
    """Выбор человека живёт в брифе, а не в аргументах каждой команды.

    Иначе панель, автономный режим и терминал звали бы стадию по-разному, и
    «чем написан сценарий» зависело бы от того, кто её запустил.
    """
    import text_stage
    from factory.text import engine as eng

    brief = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    brief.setdefault("models", {})["text"] = {
        "engine": "claude-code", "model": "opus", "effort": "xhigh"}
    (proj / "project.json").write_text(json.dumps(brief, ensure_ascii=False),
                                       encoding="utf-8")
    seen = {}

    class FakeEngine:
        name, label = "claude-code", "фейковый"

        def available(self):
            return True

        def complete(self, system, user, *, model=None, effort=None):
            seen.update(model=model, effort=effort)
            return "=== FILE: bible/idea.md ===\nтело\n=== END FILE ==="

    monkeypatch.setattr(text_stage, "pick_engine", lambda preferred=None: FakeEngine())
    monkeypatch.setattr(eng, "pick_engine", lambda preferred=None: FakeEngine())

    code = text_stage.main(["--project", str(proj), "--stage", "story"])

    assert code == 0
    assert seen == {"model": "opus", "effort": "xhigh"}
    assert "opus" in capsys.readouterr().out, "чем писалось — видно в журнале"


def test_json_output_is_not_offered_for_approval(proj, monkeypatch, capsys):
    """`shots.json` одобрять нечем: статуса у него нет, его читает съёмка.

    Совет «одобряй артефакты» печатался после любой стадии, и человек искал в
    панели то, чего там быть не может (живой прогон 2026-09-10).
    """
    import text_stage

    class FakeEngine:
        name, label = "claude-code", "фейковый"

        def available(self):
            return True

        def complete(self, system, user, *, model=None, effort=None):
            return ('=== FILE: episodes/ep01/shots.json ===\n'
                    '{"episode": "ep01", "frames": []}\n=== END FILE ===')

    monkeypatch.setattr(text_stage, "pick_engine", lambda preferred=None: FakeEngine())

    text_stage.main(["--project", str(proj), "--stage", "storyboard",
                     "--episode", "ep01"])

    out = capsys.readouterr().out
    assert "Одобрять артефакты" not in out
    assert "одобрять нечего" in out.lower() or "не артефакт" in out.lower()


def test_autonomous_mode_says_who_approves(proj, monkeypatch, capsys):
    """В автономном режиме совет «одобри руками» — прямая дезинформация."""
    import text_stage

    brief = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    brief["autonomy"] = "full"
    (proj / "project.json").write_text(json.dumps(brief, ensure_ascii=False),
                                       encoding="utf-8")

    class FakeEngine:
        name, label = "claude-code", "фейковый"

        def available(self):
            return True

        def complete(self, system, user, *, model=None, effort=None):
            return "=== FILE: bible/idea.md ===\nтело\n=== END FILE ==="

    monkeypatch.setattr(text_stage, "pick_engine", lambda preferred=None: FakeEngine())

    text_stage.main(["--project", str(proj), "--stage", "story"])

    out = capsys.readouterr().out
    assert "автономный режим" in out.lower()
    assert "factory.py approve" not in out
