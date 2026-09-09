"""Тесты панели управления (scripts/factory/webapp.py).

HTTP здесь не поднимается: проверяется чистая логика — сбор состояния проекта,
действия и containment при отдаче файлов. Сервер (scripts/serve.py) остаётся
тонкой обёрткой над этими функциями.
"""
import json
from pathlib import Path

import pytest

from factory import webapp

# Панель работает из корня репозитория; тесты чдирят в tmp, поэтому
# карточки моделей передаются явным путём.
KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"
REPO_ROOT = Path(__file__).resolve().parents[1]
from factory.manifest import Manifest

PROJECT = {
    "name": "pilot", "type": "animated_series", "theme": "маяк",
    "audience": "9-12", "episodes": 1, "episode_duration_sec": 60,
    "language": "ru", "budget_usd": 20.0,
    "models": {"image": {"model": "z_image_turbo", "provider": "wavespeed"},
               "video": {"model": "seedance_2_0", "provider": "wavespeed"}},
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / "pilot" / "episodes" / "ep01").mkdir(parents=True)
    (projects / "pilot" / "project.json").write_text(
        json.dumps(PROJECT, ensure_ascii=False), encoding="utf-8")
    (projects / "pilot" / "episodes" / "ep01" / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}],
        "segments": [{"n": 1, "start_frame": 1, "prompt": "m"}],
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return projects


# --- список проектов -------------------------------------------------------

def test_list_projects(root):
    assert webapp.list_projects(root) == ["pilot"]


def test_list_projects_skips_dirs_without_brief(root):
    (root / "мусор").mkdir()
    assert webapp.list_projects(root) == ["pilot"]


# --- состояние проекта -----------------------------------------------------

def test_overview_reports_type_and_budget(root):
    data = webapp.project_overview(root / "pilot")
    assert data["type"] == "animated_series"
    assert data["budget"]["limit"] == 20.0
    assert data["budget"]["spent"] == 0.0


def test_overview_lists_episodes_and_items(root):
    m = Manifest(root / "pilot" / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated", file="x.png")
    m.save()
    data = webapp.project_overview(root / "pilot")
    ep = data["episodes"][0]
    assert ep["id"] == "ep01"
    waiting = [i for i in ep["items"] if i["status"] == "generated"]
    assert waiting and waiting[0]["id"] == "ep01/storyboard/001"


def test_overview_reports_next_stage(root):
    data = webapp.project_overview(root / "pilot")
    # бесплатная половина не закрыта — резолвер зовёт на story
    assert data["next"]["stage"] == "story"


# --- отдача файлов: containment -------------------------------------------

def test_media_path_inside_project(root):
    f = root / "pilot" / "episodes" / "ep01" / "shots.json"
    assert webapp.media_path(root / "pilot", "episodes/ep01/shots.json") == f


def test_media_path_rejects_traversal(root):
    # панель отдаёт файлы по HTTP: ../ в запросе не должен вытаскивать чужое
    with pytest.raises(webapp.WebappError):
        webapp.media_path(root / "pilot", "../../../CLAUDE.md")


def test_media_path_rejects_absolute(root):
    with pytest.raises(webapp.WebappError):
        webapp.media_path(root / "pilot", "C:/Windows/win.ini")


def test_media_path_rejects_missing(root):
    with pytest.raises(webapp.WebappError):
        webapp.media_path(root / "pilot", "episodes/ep01/нет.png")


# --- действия --------------------------------------------------------------

def test_review_action_accepts(root):
    m = Manifest(root / "pilot" / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated")
    m.save()
    webapp.review_action(root / "pilot", "ep01/storyboard/001", "accept", None)
    assert Manifest(root / "pilot" / "manifest.json").get(
        "ep01/storyboard/001")["status"] == "done"


def test_review_action_rejects_unknown_action(root):
    with pytest.raises(webapp.WebappError, match="действие"):
        webapp.review_action(root / "pilot", "ep01/storyboard/001", "удалить", None)


def test_review_action_requires_reason_for_reject(root):
    m = Manifest(root / "pilot" / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated")
    m.save()
    with pytest.raises(webapp.WebappError, match="причин"):
        webapp.review_action(root / "pilot", "ep01/storyboard/001", "reject", "")


def test_artifacts_use_same_list_as_cli(root):
    # Панель перечисляла артефакты своим глобом bible/*.md и показывала
    # craft-notes.md как broken: это не frontmatter-артефакт. Список общий.
    (root / "pilot" / "bible").mkdir(parents=True, exist_ok=True)
    (root / "pilot" / "bible" / "craft-notes.md").write_text(
        "# Правила ремесла", encoding="utf-8")
    data = webapp.project_overview(root / "pilot")
    paths = [a["path"] for a in data["artifacts"]]
    assert "bible/craft-notes.md" not in paths
    assert "bible/idea.md" in paths


def test_manifest_file_path_is_read_relative_to_repo_root(root, monkeypatch):
    """Манифест хранит путь от КОРНЯ репозитория, не от каталога проекта.

    Генератор запускается из корня, поэтому в манифесте лежит
    `projects/pilot/...`. Считать его относительным к проекту значит получить
    `projects/pilot/projects/pilot/...` — панель показывала битые картинки.
    """
    ref = root / "pilot" / "bible" / "characters"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "Мурзик-ref.png").write_bytes(b"png")
    m = Manifest(root / "pilot" / "manifest.json")
    m.add("bible/characters/Мурзик", kind="character_ref")
    m.set_status("bible/characters/Мурзик", "generating")
    m.set_status("bible/characters/Мурзик", "generated",
                 file="projects/pilot/bible/characters/Мурзик-ref.png")
    m.save()
    data = webapp.project_overview(root / "pilot")
    assert data["character_refs"][0]["file"] == \
        "bible/characters/Мурзик-ref.png"


def test_manifest_file_outside_project_is_not_served(root):
    outside = root.parent / "чужое.png"
    outside.write_bytes(b"png")
    m = Manifest(root / "pilot" / "manifest.json")
    m.add("bible/characters/Чужой", kind="character_ref")
    m.set_status("bible/characters/Чужой", "generating")
    m.set_status("bible/characters/Чужой", "generated", file=str(outside))
    m.save()
    data = webapp.project_overview(root / "pilot")
    assert data["character_refs"][0]["file"] is None


# --- запуск стадий из панели ----------------------------------------------

class FakeRunner:
    """Реестр задач без подпроцессов: важна команда, а не её выполнение."""

    def __init__(self, busy=False):
        self.busy = busy
        self.started = None

    def start(self, cmd, meta=None):
        if self.busy:
            from factory.tasks import TaskBusyError
            raise TaskBusyError("идёт стадия segments: дождись её или отмени")
        self.started = (cmd, meta)
        return {"id": "abc", "status": "running", **(meta or {})}


def test_run_stage_rejects_unknown_stage(root):
    """Имя стадии приходит из браузера и сверяется с закрытым списком."""
    with pytest.raises(webapp.WebappError):
        webapp.run_stage(FakeRunner(), root, "pilot", "ep01", "rm -rf /")


def test_run_stage_rejects_unsafe_project_name(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_stage(FakeRunner(), root, "../secrets", "ep01", "segments")


def test_run_stage_rejects_unsafe_episode(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_stage(FakeRunner(), root, "pilot", "../../etc", "segments")


def test_run_stage_rejects_missing_project(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_stage(FakeRunner(), root, "нет-такого", "ep01", "segments")


def test_run_stage_builds_generate_batch_command(root):
    runner = FakeRunner()
    webapp.run_stage(runner, root, "pilot", "ep01", "segments")

    cmd, meta = runner.started
    assert cmd[1].endswith("generate_batch.py")
    assert "--stage" in cmd and "segments" in cmd
    assert "--episode" in cmd and "ep01" in cmd
    # Смету панель показала до запуска, второй вопрос в терминале некому увидеть.
    assert "--yes" in cmd
    assert meta["stage"] == "segments"


def test_run_stage_render_uses_render_script(root):
    runner = FakeRunner()
    webapp.run_stage(runner, root, "pilot", "ep01", "render")

    cmd, meta = runner.started
    assert cmd[1].endswith("render.py")
    assert "--yes" not in cmd          # render ничего не тратит и не спрашивает
    assert meta["kind"] == "render"


def test_run_stage_while_busy_explains_what_is_running(root):
    with pytest.raises(webapp.WebappError) as e:
        webapp.run_stage(FakeRunner(busy=True), root, "pilot", "ep01", "audio")
    assert "segments" in str(e.value)


# --- смета -----------------------------------------------------------------

def test_stage_estimate_counts_pending_work(root):
    est = webapp.episode_estimate(root / "pilot", "ep01", KNOWLEDGE)

    stages = {row["stage"]: row for row in est["rows"]}
    assert stages["storyboard"]["count"] == 2
    assert stages["segments"]["count"] == 1
    assert est["total"] > 0
    assert est["budget"]["limit"] == 20.0


def test_stage_estimate_skips_accepted_work(root):
    manifest = Manifest(root / "pilot" / "manifest.json")
    manifest.add("ep01/storyboard/001", "frame")
    # Статусы конвейера идут цепочкой: снято -> принято. Прыгнуть сразу в done
    # манифест не даёт, и это не придирка — принять можно только снятое.
    manifest.set_status("ep01/storyboard/001", "generating")
    manifest.set_status("ep01/storyboard/001", "generated")
    manifest.set_status("ep01/storyboard/001", "done")
    manifest.save()          # смета читает файл, а не чужую память

    est = webapp.episode_estimate(root / "pilot", "ep01", KNOWLEDGE)
    stages = {row["stage"]: row for row in est["rows"]}
    assert stages["storyboard"]["count"] == 1


# --- балансы ---------------------------------------------------------------

def test_balances_report_none_where_provider_cannot_tell(monkeypatch):
    monkeypatch.setenv("WAVESPEED_API_KEY", "ws-test")
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-test")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from factory.providers.wavespeed import WaveSpeedProvider
    monkeypatch.setattr(WaveSpeedProvider, "balance", lambda self: 41.07)

    rows = {r["provider"]: r for r in webapp.balances()}
    assert rows["WaveSpeed"]["balance"] == 41.07
    assert rows["Runware"]["balance"] is None
    assert "не отдаёт" in rows["Runware"]["reason"]
    assert rows["OpenRouter"]["reason"] and rows["OpenRouter"]["balance"] is None


# --- смета знает жанр и режим ---------------------------------------------

def _retype(root, **fields):
    path = root / "pilot" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _drop_segments(root):
    """Режим кадров в ПЛАНЕ: отрезков нет вовсе.

    Смета читает план, а не флаг проекта, — тот же источник, что у приёмки и у
    монтажного листа. Флаг остаётся входом стадии раскадровки.
    """
    path = root / "pilot" / "episodes" / "ep01" / "shots.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["segments"] = []
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")


def test_stills_mode_does_not_charge_for_segments(root):
    """В режиме кадров отрезки не снимаются — платить за них не за что."""
    _retype(root, genre="educational", visual_mode="stills")
    _drop_segments(root)

    est = webapp.episode_estimate(root / "pilot", "ep01", KNOWLEDGE)
    stages = {row["stage"] for row in est["rows"]}
    assert "storyboard" in stages
    assert "segments" not in stages


def test_video_mode_still_charges_for_segments(root):
    _retype(root, genre="educational", visual_mode="video")

    est = webapp.episode_estimate(root / "pilot", "ep01", KNOWLEDGE)
    assert "segments" in {row["stage"] for row in est["rows"]}


# --- панель знает жанр, язык и режим --------------------------------------

def test_overview_reports_genre_card(root):
    _retype(root, genre="educational")
    data = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert data["genre"]["id"] == "educational"
    assert data["genre"]["label"] == "Познавательное"
    assert "characters" not in data["genre"]["stages"]
    assert data["genre"]["lipsync"] is False


def test_overview_reports_language_and_mode(root):
    _retype(root, genre="educational", language="ru")
    data = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert data["language"] == "ru"
    assert data["visual_mode"] == "stills"
    assert {"code": "ru", "label": "Русский"} in data["languages"]
    assert set(data["visual_modes"]) == {"stills", "video"}


def test_overview_offers_single_mode_where_genre_allows_one(root):
    """Переключатель не должен предлагать то, чего жанр не допускает."""
    _retype(root, genre="animation")
    data = webapp.project_overview(root / "pilot", KNOWLEDGE)
    assert data["visual_modes"] == ["video"]


def test_set_language_writes_brief(root):
    webapp.set_project_settings(root / "pilot", {"language": "ru"}, KNOWLEDGE)
    saved = json.loads((root / "pilot" / "project.json").read_text(encoding="utf-8"))
    assert saved["language"] == "ru"


def test_set_visual_mode_writes_brief(root):
    _retype(root, genre="educational")
    webapp.set_project_settings(root / "pilot", {"visual_mode": "video"}, KNOWLEDGE)
    saved = json.loads((root / "pilot" / "project.json").read_text(encoding="utf-8"))
    assert saved["visual_mode"] == "video"


def test_unknown_language_rejected(root):
    with pytest.raises(webapp.WebappError):
        webapp.set_project_settings(root / "pilot", {"language": "эльфийский"}, KNOWLEDGE)


def test_mode_not_allowed_by_genre_rejected(root):
    """Кино слайдшоу не снимают — панель не должна давать это выбрать."""
    _retype(root, genre="animation")
    with pytest.raises(webapp.WebappError):
        webapp.set_project_settings(root / "pilot", {"visual_mode": "stills"}, KNOWLEDGE)


def test_settings_keep_other_fields_intact(root):
    """Правка одного поля не должна терять бриф: там тема, бюджет и модели."""
    webapp.set_project_settings(root / "pilot", {"language": "ru"}, KNOWLEDGE)
    saved = json.loads((root / "pilot" / "project.json").read_text(encoding="utf-8"))
    assert saved["theme"] == PROJECT["theme"]
    assert saved["models"] == PROJECT["models"]
    assert saved["budget_usd"] == PROJECT["budget_usd"]


# --- текстовые стадии в панели --------------------------------------------

class FakeEngine:
    name = "fake"
    label = "Тестовый движок"

    def __init__(self, answer="=== FILE: bible/idea.md ===\nновая идея\n=== END FILE ==="):
        self.answer = answer
        self.seen = None

    def available(self):
        return True

    def complete(self, system, user, *, model=None):
        self.seen = (system, user, model)
        return self.answer


def test_text_stage_writes_declared_artifact(root, monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr(webapp.text_engine, "pick_engine", lambda preferred=None: engine)

    result = webapp.run_text_stage(root / "pilot", "story", request="про маяк",
                                   repo_root=REPO_ROOT)

    assert result["written"] == ["bible/idea.md"]
    assert "новая идея" in (root / "pilot" / "bible" / "idea.md").read_text("utf-8")
    # Промпт собран из скилла: методика не переписана в панель.
    assert "Библия" in engine.seen[0] or "идея" in engine.seen[0].lower()
    assert "про маяк" in engine.seen[1]


def test_pitch_returns_answer_and_writes_nothing(root, monkeypatch):
    """Питч — разговор: три варианта показываются, файлы не трогаются."""
    engine = FakeEngine(answer="Вариант 1… Вариант 2… Вариант 3…")
    monkeypatch.setattr(webapp.text_engine, "pick_engine", lambda preferred=None: engine)

    result = webapp.run_text_stage(root / "pilot", "pitch", request="",
                                   repo_root=REPO_ROOT)

    assert result["written"] == []
    assert "Вариант 1" in result["answer"]


def test_text_stage_rejects_unknown_stage(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_text_stage(root / "pilot", "нет-такой", repo_root=REPO_ROOT)


def test_text_stage_reports_engine_failure(root, monkeypatch):
    class Broken(FakeEngine):
        def complete(self, system, user, *, model=None):
            from factory.text.engine import TextEngineError
            raise TextEngineError("модель отказала")

    monkeypatch.setattr(webapp.text_engine, "pick_engine",
                        lambda preferred=None: Broken())
    with pytest.raises(webapp.WebappError) as e:
        webapp.run_text_stage(root / "pilot", "story", repo_root=REPO_ROOT)
    assert "модель отказала" in str(e.value)


def test_text_stages_listed_for_genre(root):
    _retype(root, genre="educational")
    listed = {s["id"] for s in webapp.text_stages(root / "pilot", KNOWLEDGE)}

    assert "story" in listed
    assert "characters" not in listed, "у познавательного нет персонажей"
    assert "research" in listed


def test_text_task_builds_command_for_cli(root):
    runner = FakeRunner()
    webapp.run_text_task(runner, root, "pilot", "story", request="про маяк",
                         repo_root=REPO_ROOT)

    cmd, meta = runner.started
    assert cmd[1].endswith("text_stage.py")
    assert "--stage" in cmd and "story" in cmd
    assert "--request" in cmd and "про маяк" in cmd
    assert meta["kind"] == "text"


def test_text_task_rejects_unknown_stage(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_text_task(FakeRunner(), root, "pilot", "rm -rf",
                             repo_root=REPO_ROOT)


def test_text_task_rejects_unsafe_names(root):
    with pytest.raises(webapp.WebappError):
        webapp.run_text_task(FakeRunner(), root, "../secrets", "story",
                             repo_root=REPO_ROOT)
    with pytest.raises(webapp.WebappError):
        webapp.run_text_task(FakeRunner(), root, "pilot", "script",
                             episode="../..", repo_root=REPO_ROOT)


# --- следующий шаг знает, чем его запускать --------------------------------

def test_next_step_says_which_runner_it_needs(root):
    """Панель не решает сама, платная стадия или текстовая: кнопка, решающая
    это самостоятельно, однажды отправит платную стадию мимо сметы."""
    view = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert view["next"]["kind"] in ("text", "paid")
    assert view["next"]["stage"]


def test_paid_and_text_stages_are_split_by_the_same_lists():
    from factory.preprod import PAID_STAGES

    for stage in PAID_STAGES:
        assert webapp._next_step((stage, "ep01"))["kind"] == "paid"
    for stage in webapp.TEXT_RUNNABLE:
        if stage in PAID_STAGES:
            continue
        assert webapp._next_step((stage, "ep01"))["kind"] == "text"


def test_unknown_stage_is_named_not_hidden():
    """Молча спрятать кнопку значит соврать, что делать нечего."""
    assert webapp._next_step(("невиданное", None))["kind"] == "unknown"


def test_no_next_step_is_none():
    assert webapp._next_step(None) is None


# --- находки ревью конвейера 2026-09-09 -----------------------------------

def test_next_step_gives_a_stage_the_panel_can_actually_run():
    """Резолвер называет `storyboard_generate`, а CLI знает `storyboard`.

    Кнопка «Запустить конвейер» отправляла имя резолвера прямо в запуск и
    получала «неизвестная стадия»: конвейер вставал ровно на первом платном
    шаге. Перевод имени — одно место (`preprod.cli_stage`), панель его только
    показывает.
    """
    step = webapp._next_step(("storyboard_generate", "ep01"))

    assert step["kind"] == "paid"
    assert step["run"] in webapp.RUNNABLE_STAGES
    assert step["run"] == "storyboard"


def test_next_step_run_name_matches_stage_for_ordinary_paid_stages():
    for name in ("segments", "audio", "foley", "lipsync", "render"):
        assert webapp._next_step((name, "ep01"))["run"] == name


def test_next_step_text_stage_is_runnable_by_the_panel():
    step = webapp._next_step(("audio_plan", "ep01"))
    assert step["kind"] == "text"
    assert step["run"] in webapp.TEXT_RUNNABLE


def test_switching_visual_mode_warns_about_the_written_plan(root):
    """Режим берётся из плана, поэтому один флаг ничего не переключает.

    Человек, поставивший «кадры» на проекте с уже написанной раскадровкой,
    иначе решил бы, что отрезки сниматься не будут, — а конвейер продолжил бы
    снимать их по старому плану и списал деньги.
    """
    _retype(root, genre="educational")

    result = webapp.set_project_settings(root / "pilot",
                                         {"visual_mode": "stills"}, KNOWLEDGE)

    assert result["visual_mode"] == "stills"
    assert any("ep01" in w for w in result["warnings"])
    assert any("storyboard" in w for w in result["warnings"])


def test_no_warning_when_the_plan_already_matches_the_mode(root):
    _retype(root, genre="educational")
    _drop_segments(root)

    result = webapp.set_project_settings(root / "pilot",
                                         {"visual_mode": "stills"}, KNOWLEDGE)

    assert result["warnings"] == []


# --- автономный и ручной режим (2026-09-09) --------------------------------

def test_overview_reports_autonomy_manual_by_default(root):
    """Молчание брифа — РУЧНОЙ режим: деньги без спроса не тратятся."""
    data = webapp.project_overview(root / "pilot", KNOWLEDGE)
    assert data["autonomy"] == "checkpoints"


def test_autonomy_full_does_not_demand_a_budget_ceiling(root):
    """Потолок автономному режиму не обязателен (решение 2026-09-09).

    Тормоз там другой: смета всего остатка, показанная перед стартом, и одно
    подтверждение человека. Требование выдумать число мешало включить режим.
    """
    _retype(root, budget_usd=None)

    webapp.set_project_settings(root / "pilot", {"autonomy": "full"}, KNOWLEDGE)

    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["autonomy"] == "full"


def test_autonomy_switches_both_ways(root):
    webapp.set_project_settings(root / "pilot", {"autonomy": "full"}, KNOWLEDGE)
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["autonomy"] == "full"

    webapp.set_project_settings(root / "pilot", {"autonomy": "checkpoints"}, KNOWLEDGE)
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["autonomy"] == "checkpoints"


def test_unknown_autonomy_is_refused(root):
    with pytest.raises(webapp.WebappError):
        webapp.set_project_settings(root / "pilot", {"autonomy": "как-нибудь"},
                                    KNOWLEDGE)


# --- длительность отрезка и серии ------------------------------------------

def _gridded_video_model(root):
    """Видеомодель с объявленной сеткой длительностей (seedance1_5: 4, 8, 12)."""
    _retype(root, models={"image": {"model": "z_image_turbo",
                                    "provider": "wavespeed"},
                          "video": {"model": "seedance1_5",
                                    "provider": "wavespeed"}},
            segment_seconds=8)


def test_overview_offers_the_durations_the_model_allows(root):
    """Свободный ввод обещал бы длительность, которую гейт модели отобьёт."""
    _gridded_video_model(root)

    data = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert data["segment_options"] == [4, 8, 12]
    assert data["segment_seconds"] in data["segment_options"]


def test_no_grid_means_no_options_not_a_made_up_list(root):
    """У seedance 2.0 сетка не объявлена: выдуманный список врал бы человеку."""
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["segment_options"] == []


def test_segment_seconds_is_written_and_validated(root):
    _gridded_video_model(root)

    webapp.set_project_settings(root / "pilot", {"segment_seconds": 4}, KNOWLEDGE)
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["segment_seconds"] == 4

    # 7 секунд эта модель не снимает — отказ здесь, а не на платной стадии.
    with pytest.raises(webapp.WebappError, match="7"):
        webapp.set_project_settings(root / "pilot", {"segment_seconds": 7}, KNOWLEDGE)
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["segment_seconds"] == 4


def test_segment_seconds_refuses_nonsense(root):
    for bad in (0, -5, "десять", 2.5, True):
        with pytest.raises(webapp.WebappError):
            webapp.set_project_settings(root / "pilot", {"segment_seconds": bad},
                                        KNOWLEDGE)


def test_overview_tells_how_long_the_episode_will_be(root):
    """Один отрезок по 5 с — эпизод на 5 с, при цели брифа в 60."""
    data = webapp.project_overview(root / "pilot", KNOWLEDGE)
    ep = data["episodes"][0]

    assert ep["duration"]["planned_sec"] == 5
    assert ep["duration"]["target_sec"] == 60
    assert ep["duration"]["exact"] is True


def test_stills_duration_is_a_minimum_not_a_promise(root):
    """В режиме кадров длительность задаёт реплика, и её меряет монтаж."""
    _retype(root, genre="educational", visual_mode="stills")
    _drop_segments(root)

    ep = webapp.project_overview(root / "pilot", KNOWLEDGE)["episodes"][0]

    assert ep["duration"]["exact"] is False
    assert ep["duration"]["planned_sec"] > 0


# --- приёмка текстов -------------------------------------------------------

def test_written_but_unapproved_text_waits_for_the_human(root):
    """Тексты ждут человека так же, как кадры: место у них одно — приёмка."""
    idea = root / "pilot" / "bible" / "idea.md"
    idea.parent.mkdir(parents=True, exist_ok=True)
    idea.write_text("---\nkind: idea\nstatus: draft\n---\nмаяк и ворона\n",
                    encoding="utf-8")

    data = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert any(a["path"] == "bible/idea.md" for a in data["awaiting_text"])


def test_empty_scaffold_is_not_waiting_for_anything(root):
    """Пустой артефакт скаффолда никто не писал — приёмке он не подлежит."""
    idea = root / "pilot" / "bible" / "idea.md"
    idea.parent.mkdir(parents=True, exist_ok=True)
    idea.write_text("---\nkind: idea\nstatus: draft\n---\n\n", encoding="utf-8")

    data = webapp.project_overview(root / "pilot", KNOWLEDGE)

    assert data["awaiting_text"] == []


# --- удаление проекта ------------------------------------------------------

def test_delete_project_removes_the_directory(root):
    webapp.delete_project(root, "pilot", confirm="pilot")
    assert webapp.list_projects(root) == []


def test_delete_refuses_without_the_exact_name(root):
    """Удаление уносит оплаченные генерации: подтверждение — точное имя."""
    with pytest.raises(webapp.WebappError):
        webapp.delete_project(root, "pilot", confirm="pilo")
    assert webapp.list_projects(root) == ["pilot"]


def test_delete_refuses_a_name_that_is_not_a_project(root):
    with pytest.raises(webapp.WebappError):
        webapp.delete_project(root, "../..", confirm="../..")
    assert (root / "pilot").exists()


def test_unknown_setting_is_refused_not_swallowed(root):
    """Незнакомое поле — отказ, а не тишина.

    У сервера был свой список настраиваемых полей, и новая настройка молча
    терялась по дороге: панель говорила «Сохранено», в бриф не попадало ничего.
    """
    with pytest.raises(webapp.WebappError, match="настраивает"):
        webapp.set_project_settings(root / "pilot", {"theme": "другая"}, KNOWLEDGE)


def test_budget_ceiling_is_set_from_the_panel(root):
    """Потолок — условие автономного режима, значит его должно быть где задать."""
    webapp.set_project_settings(root / "pilot", {"budget_usd": 12.5}, KNOWLEDGE)
    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["budget"]["limit"] == 12.5

    for bad in (-1, 0, "много"):
        with pytest.raises(webapp.WebappError):
            webapp.set_project_settings(root / "pilot", {"budget_usd": bad},
                                        KNOWLEDGE)


def test_budget_can_be_removed_in_any_mode(root):
    """Потолок — не условие режима, а необязательное ограничение сверху."""
    webapp.set_project_settings(root / "pilot", {"autonomy": "full"}, KNOWLEDGE)

    webapp.set_project_settings(root / "pilot", {"budget_usd": None}, KNOWLEDGE)

    assert webapp.project_overview(root / "pilot", KNOWLEDGE)["budget"]["limit"] is None


# --- смета всего прогона (перед стартом автономного режима) ----------------

def test_project_estimate_sums_every_episode(root):
    """Автономный прогон идёт по всем сериям, значит и смета — по всем."""
    est = webapp.project_estimate(root / "pilot", KNOWLEDGE)

    assert [e["episode"] for e in est["episodes"]] == ["ep01"]
    assert est["total"] == pytest.approx(sum(e["total"] for e in est["episodes"]))
    assert est["total"] > 0


def test_project_estimate_survives_an_episode_without_a_plan(root):
    """Серия без раскадровки — не повод не показать смету по остальным."""
    _retype(root, episodes=2)

    est = webapp.project_estimate(root / "pilot", KNOWLEDGE)

    assert [e["episode"] for e in est["episodes"]] == ["ep01"]
    assert any("ep02" in p for p in est["problems"])


def test_project_estimate_reports_the_ceiling_when_it_is_set(root):
    est = webapp.project_estimate(root / "pilot", KNOWLEDGE)
    assert est["budget"]["limit"] == 20.0

    webapp.set_project_settings(root / "pilot", {"budget_usd": None}, KNOWLEDGE)
    assert webapp.project_estimate(root / "pilot", KNOWLEDGE)["budget"] is None


def test_missing_shot_plan_reads_as_unwritten_work_not_as_a_failure(root):
    """«Раскадровки ещё нет» — это состояние конвейера, а не поломка.

    Перед стартом автономного прогона человек видит смету; строка с
    `[Errno 2] No such file or directory` читается там как сбой панели, хотя
    означает всего лишь, что план съёмки этой серии ещё предстоит написать.
    """
    _retype(root, episodes=2)

    problems = webapp.project_estimate(root / "pilot", KNOWLEDGE)["problems"]

    assert any("ep02" in p and "не написан" in p for p in problems)
    assert not any("Errno" in p for p in problems)
