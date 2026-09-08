"""Проверка фактов познавательного жанра: maker-checker, поиск, гейт одобрения.

Сети здесь нет: движок и поисковый провайдер подменяются заглушками. Проверяется
не то, что модель умная, а то, что конвейер не выдаёт непроверенное за
проверенное — ради этого стадия и заводилась.
"""
import json
from pathlib import Path

import pytest

from factory import preprod
from factory.providers import ProviderError, get_search_provider
from factory.providers.tavily import TavilyProvider
from factory.text import factcheck

REPO = Path(__file__).resolve().parents[1]
KNOWLEDGE = REPO / "knowledge"

SCRIPT = """---
kind: script
status: draft
characters: []
---
Диктор: Аполлон-11 сел на Луну в 1969 году.
"""

CLAIMS_ANSWER = """Проверяемых утверждений одно.

=== CLAIM ===
утверждение: Аполлон-11 сел на Луну в 1969 году
запрос: Apollo 11 Moon landing 1969
=== END CLAIM ===
"""

VERDICT_ANSWER = """=== VERDICT: passed ===

=== FILE: episodes/ep01/fact-check.md ===
| утверждение | вердикт |
|---|---|
| Аполлон-11 сел на Луну в 1969 | подтверждено |
=== END FILE ===
"""


class FakeEngine:
    """Движок без сети: отдаёт заготовленные ответы по одному на вызов."""
    label = "фейковый движок"

    def __init__(self, answers, name="fake"):
        self.name = name
        self._answers = list(answers)
        self.calls = []

    def available(self):
        return True

    def complete(self, system, user, *, model=None):
        self.calls.append({"system": system, "user": user, "model": model})
        if not self._answers:
            raise AssertionError("движок позвали больше раз, чем ожидалось")
        return self._answers.pop(0)


class FakeSearch:
    name = "fake-search"

    def __init__(self, results=None, fail=False):
        self.results = results if results is not None else [
            {"title": "NASA", "url": "https://nasa.gov/apollo11",
             "snippet": "20 июля 1969", "score": 0.9}]
        self.fail = fail
        self.queries = []

    def search(self, query, *, max_results=8):
        self.queries.append(query)
        if self.fail:
            raise ProviderError("сеть отвалилась")
        return self.results


@pytest.fixture
def project(tmp_path):
    """Познавательный проект с написанным, но неодобренным сценарием."""
    pdir = tmp_path / "познавательный"
    (pdir / "bible").mkdir(parents=True)
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "познавательный", "type": "series", "genre": "educational",
        "theme": "космос", "episodes": 1, "episode_duration_sec": 60,
        "language": "ru",
        "models": {"image": {"model": "z_image_turbo"},
                   "video": {"model": "vidu_q2_turbo"}},
    }, ensure_ascii=False), encoding="utf-8")
    (pdir / "episodes" / "ep01" / "script.md").write_text(SCRIPT, encoding="utf-8")
    return pdir


@pytest.fixture
def cartoon(tmp_path):
    """Мультфильм: проверять факты нечего и требовать её нельзя."""
    pdir = tmp_path / "мультик"
    (pdir / "bible").mkdir(parents=True)
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "мультик", "type": "animated_series", "audience": "6+",
        "theme": "маяк", "episodes": 1, "episode_duration_sec": 60,
        "language": "ru",
        "models": {"image": {"model": "z_image_turbo"},
                   "video": {"model": "vidu_q2_turbo"}},
    }, ensure_ascii=False), encoding="utf-8")
    (pdir / "episodes" / "ep01" / "script.md").write_text(SCRIPT, encoding="utf-8")
    return pdir


# --- поисковый провайдер ---------------------------------------------------

def test_tavily_shapes_results_and_hides_provider_fields(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-тест")
    p = TavilyProvider()
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None: {
        "results": [{"title": "NASA", "url": "https://nasa.gov", "content": "текст",
                     "score": 0.9, "favicon": "мусор"}]})

    found = p.search("apollo 11")

    assert found == [{"title": "NASA", "url": "https://nasa.gov",
                      "snippet": "текст", "score": 0.9}]


def test_tavily_rejects_empty_query_before_spending_a_credit(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-тест")
    p = TavilyProvider()
    monkeypatch.setattr(p, "_request", lambda *a, **k: pytest.fail("сеть не нужна"))

    with pytest.raises(ProviderError):
        p.search("   ")


def test_tavily_refuses_answer_without_results(monkeypatch):
    """Пустой список вместо ошибки заставил бы проверяющего завалить верный факт."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-тест")
    p = TavilyProvider()
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None: {"detail": "429"})

    with pytest.raises(ProviderError):
        p.search("apollo 11")


def test_tavily_asks_for_deep_excerpts_and_no_generated_answer(monkeypatch):
    """Ответ самой Tavily — ещё один пересказ; источники смотрим сами."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-тест")
    p = TavilyProvider()
    sent = {}

    def fake(method, url, json_body=None):
        sent.update({"method": method, "url": url, "body": json_body})
        return {"results": []}

    monkeypatch.setattr(p, "_request", fake)
    p.search("apollo 11")

    assert sent["method"] == "POST"
    assert sent["body"]["search_depth"] == "advanced"
    assert sent["body"]["include_answer"] is False
    assert sent["body"]["max_results"] >= 5


def test_search_provider_without_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert TavilyProvider().available() is False
    with pytest.raises(ProviderError):
        get_search_provider()


# --- доступность -----------------------------------------------------------

def test_unavailable_without_search_key_and_without_agent(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    ok, reason = factcheck.availability()

    assert ok is False
    assert "TAVILY_API_KEY" in reason and "Claude Code" in reason


def test_agent_can_check_without_search_key(monkeypatch):
    """Claude Code ищет своими инструментами — отдельный ключ ему не нужен."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    ok, _ = factcheck.availability(FakeEngine([], name="claude-code"))

    assert ok is True


def test_model_by_key_cannot_check_without_search_key(monkeypatch):
    """У модели по ключу инструментов поиска нет: без Tavily ей нечем проверять."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "C:/claude.exe")

    ok, reason = factcheck.availability(FakeEngine([], name="openrouter"))

    assert ok is False
    assert reason


# --- разбор ответов --------------------------------------------------------

def test_parse_claims_reads_statement_and_query():
    claims = factcheck.parse_claims(CLAIMS_ANSWER)
    assert len(claims) == 1
    assert claims[0].text.startswith("Аполлон-11")
    assert claims[0].query == "Apollo 11 Moon landing 1969"


def test_parse_claims_allows_zero_claims():
    assert factcheck.parse_claims("проверяемых утверждений нет") == []


def test_claim_without_query_is_an_error():
    """Утверждение без запроса нечем проверять — пропустить его нельзя."""
    with pytest.raises(factcheck.FactCheckError):
        factcheck.parse_claims(
            "=== CLAIM ===\nутверждение: земля круглая\n=== END CLAIM ===")


def test_parse_verdict_reads_both_values():
    assert factcheck.parse_verdict("=== VERDICT: passed ===") == "passed"
    assert factcheck.parse_verdict("текст\n=== VERDICT: failed ===\n") == "failed"


def test_missing_verdict_is_an_error_not_a_guess():
    with pytest.raises(factcheck.FactCheckError):
        factcheck.parse_verdict("всё хорошо, я проверил")


# --- поиск между проходами -------------------------------------------------

def test_failed_search_is_reported_not_swallowed():
    claims = factcheck.parse_claims(CLAIMS_ANSWER)
    factcheck.gather(claims, FakeSearch(fail=True), log=lambda *_: None)

    assert claims[0].sources == []
    assert "сеть отвалилась" in claims[0].error


def test_verdict_task_carries_found_sources():
    claims = factcheck.parse_claims(CLAIMS_ANSWER)
    factcheck.gather(claims, FakeSearch(), log=lambda *_: None)

    task = factcheck.verdict_task(claims, searched=True)

    assert "https://nasa.gov/apollo11" in task
    assert "20 июля 1969" in task


def test_verdict_task_tells_agent_to_search_itself_when_no_excerpts():
    claims = factcheck.parse_claims(CLAIMS_ANSWER)
    task = factcheck.verdict_task(claims, searched=False)
    assert "ищи сам" in task


def test_claims_over_the_cap_go_marked_unsearched():
    """Потолок режет расходы, а не список: непроверенное обязано быть названо."""
    claims = [factcheck.Claim(text=f"утв {i}", query=f"q{i}") for i in range(3)]
    search = FakeSearch()
    factcheck.gather(claims, search, max_searches=2, log=lambda *_: None)

    assert search.queries == ["q0", "q1"]
    assert claims[2].sources is None
    assert "НЕ проводился" in factcheck.verdict_task(claims, searched=True)


# --- прогон целиком --------------------------------------------------------

def test_run_writes_report_and_stamps_script_hash(project):
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER])

    result = factcheck.run(project, REPO, "ep01", engine=engine,
                           search=FakeSearch(), log=lambda *_: None)

    assert result["verdict"] == "passed"
    report = project / "episodes" / "ep01" / "fact-check.md"
    assert report.is_file()
    body = report.read_text(encoding="utf-8")
    assert "verdict: passed" in body
    assert "script_sha:" in body
    assert preprod.artifact_state(project, report) == "draft"


def test_checker_never_sees_how_the_script_was_written(project):
    """Пустой контекст: ни идеи, ни арки, ни правил ремесла в промпте нет."""
    (project / "bible" / "idea.md").write_text(
        "---\nstatus: approved\n---\nсекретный замысел автора\n", encoding="utf-8")
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER])

    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)

    for call in engine.calls:
        assert "секретный замысел" not in call["user"]


def test_correction_keeps_script_frontmatter(project):
    """Правка фактов не смеет затирать состав серии: он живёт во frontmatter."""
    (project / "episodes" / "ep01" / "script.md").write_text(
        "---\nkind: script\nstatus: draft\ncharacters: [Диктор]\n---\n"
        "Диктор: Аполлон-11 сел на Луну в 1970 году.\n", encoding="utf-8")
    fixed = """=== VERDICT: passed ===

=== FILE: episodes/ep01/script.md ===
Диктор: Аполлон-11 сел на Луну в 1969 году.
=== END FILE ===

=== FILE: episodes/ep01/fact-check.md ===
исправлено: 1970 → 1969
=== END FILE ===
"""
    engine = FakeEngine([CLAIMS_ANSWER, fixed])

    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)

    script = (project / "episodes" / "ep01" / "script.md").read_text("utf-8")
    assert "characters:" in script and "Диктор" in script
    assert "1969" in script and "1970" not in script


def test_verdict_without_report_is_refused(project):
    """Вердикт без отчёта — не документ: проверить его человеку нечем."""
    engine = FakeEngine([CLAIMS_ANSWER, """=== VERDICT: passed ===

=== FILE: episodes/ep01/script.md ===
тело
=== END FILE ===
"""])

    with pytest.raises(factcheck.FactCheckError):
        factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                      log=lambda *_: None)


def test_run_refuses_unsafe_episode_name(project):
    with pytest.raises(factcheck.FactCheckError):
        factcheck.run(project, REPO, "../../секреты", engine=FakeEngine([]),
                      search=FakeSearch(), log=lambda *_: None)


# --- вердикт как состояние проекта ----------------------------------------

def test_problem_when_check_never_ran(project):
    assert "проверки фактов не было" in factcheck.report_problem(project, "ep01")


def test_problem_when_verdict_failed(project):
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER.replace("passed", "failed")])
    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)

    assert "не пройдена" in factcheck.report_problem(project, "ep01")


def test_passed_check_leaves_no_problem(project):
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER])
    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)

    assert factcheck.report_problem(project, "ep01") is None


def test_editing_the_script_invalidates_the_check(project):
    """«Проверено» относится к тексту, а не к имени файла."""
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER])
    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)
    script = project / "episodes" / "ep01" / "script.md"
    script.write_text(SCRIPT.replace("1969", "1970"), encoding="utf-8")

    assert "другой версии сценария" in factcheck.report_problem(project, "ep01")


# --- гейты конвейера -------------------------------------------------------

def _approve(path: Path, body: str) -> None:
    """Одобренный артефакт: content_sha обязан совпасть с телом."""
    from factory.artifact import Artifact, save_artifact

    art = Artifact(path=path, meta={"status": "approved"}, body=body)
    art.meta["content_sha"] = art.sha
    save_artifact(art)



def test_cartoon_never_needs_a_fact_check(cartoon):
    assert preprod.fact_check_problem(cartoon, "ep01") is None


def test_educational_script_stage_lists_the_check_as_its_own_work(project):
    blockers, own_work = preprod.stage_problems(project, "script", "ep01")

    # Ненаписанная библия — чужой вход и настоящий блокер; непроверенные факты —
    # работа самого этапа script, и путать эти два списка нельзя (U-11).
    assert any("проверки фактов не было" in p for p in own_work)
    assert not any("проверки фактов" in p for p in blockers)


def test_storyboard_is_blocked_until_facts_are_checked(project):
    blockers, _ = preprod.stage_problems(project, "storyboard", "ep01")
    assert any("проверк" in p for p in blockers)


def test_research_comes_before_everything_for_this_genre(project):
    """У познавательного жанра исследование — первая фаза, и резолвер
    начинает с неё, а не с идеи."""
    assert preprod.next_stage(project) == ("research", None)


def test_next_stage_sends_written_script_to_the_check(project):
    _approve(project / "research.md", "источники")
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"):
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nstatus: draft\n---\nтекст\n", encoding="utf-8")

    # Пока библия не одобрена, очередь у неё — проверка ждёт своей очереди.
    assert preprod.next_stage(project) == ("story", None)


def test_next_stage_prefers_factcheck_over_rewriting_the_script(project, monkeypatch):
    _approve(project / "research.md", "источники")
    monkeypatch.setattr(preprod, "artifact_state",
                        lambda pdir, path: "approved"
                        if "script.md" not in str(path) else "draft")

    assert preprod.next_stage(project) == ("factcheck", "ep01")


def test_factcheck_stage_gate_needs_a_script(project):
    (project / "episodes" / "ep01" / "script.md").unlink()

    blockers, _ = preprod.stage_problems(project, "factcheck", "ep01")

    assert any("сначала этап script" in p for p in blockers)


def test_factcheck_stage_does_not_exist_for_a_cartoon(cartoon):
    blockers, _ = preprod.stage_problems(cartoon, "factcheck", "ep01")
    assert any("не существует у этого жанра" in p for p in blockers)


def test_factcheck_gate_open_after_a_passed_check(project, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-тест")
    engine = FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER])
    factcheck.run(project, REPO, "ep01", engine=engine, search=FakeSearch(),
                  log=lambda *_: None)

    assert preprod.stage_gate(project, "factcheck", "ep01") == []


# --- одобрение сценария ----------------------------------------------------

def _bible(project):
    """Зависимости сценария: без них approve откажет по другой причине."""
    for rel in ("bible/idea.md", "bible/season-arc.md"):
        path = project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nstatus: draft\n---\nтекст\n", encoding="utf-8")


def test_approve_refuses_an_unchecked_educational_script(project, capsys):
    """Одна дверь, один замок: approve — единственное место, ставящее approved."""
    import factory_cli_entry as fc
    _bible(project)

    code = fc.main(["approve", "--project", str(project),
                    "episodes/ep01/script.md"])

    assert code == 3
    assert "факты не проверены" in capsys.readouterr().out
    assert preprod.artifact_state(project, project / "episodes/ep01/script.md") \
        == "draft"


def test_approve_passes_after_a_successful_check(project):
    import factory_cli_entry as fc
    _bible(project)
    factcheck.run(project, REPO, "ep01",
                  engine=FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER]),
                  search=FakeSearch(), log=lambda *_: None)

    code = fc.main(["approve", "--project", str(project),
                    "episodes/ep01/script.md"])

    assert code == 0
    assert preprod.artifact_state(project, project / "episodes/ep01/script.md") \
        == "approved"


def test_approve_of_a_cartoon_script_is_untouched(cartoon):
    """Жанру без проверки фактов новая дверь ничего не закрывает."""
    import factory_cli_entry as fc
    _bible(cartoon)

    assert fc.main(["approve", "--project", str(cartoon),
                    "episodes/ep01/script.md"]) == 0


# --- панель ----------------------------------------------------------------

def test_panel_shows_the_check_only_where_the_genre_demands_it(project, cartoon):
    from factory import webapp

    assert "factcheck" in {s["id"] for s in webapp.text_stages(project, KNOWLEDGE)}
    assert "factcheck" not in {s["id"]
                               for s in webapp.text_stages(cartoon, KNOWLEDGE)}


def test_panel_says_why_the_check_is_unavailable(project, monkeypatch):
    """Кнопка, которая молча откажет, хуже кнопки с причиной."""
    from factory import webapp
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    row = next(s for s in webapp.text_stages(project, KNOWLEDGE)
               if s["id"] == "factcheck")

    assert "TAVILY_API_KEY" in row["blocked"]


# --- панель показывает проверку -------------------------------------------

def test_panel_block_absent_for_a_genre_that_does_not_check(cartoon, monkeypatch):
    """Пустой блок на экране мультфильма — обещание работы, которой не будет."""
    from factory import webapp
    monkeypatch.chdir(cartoon.parent)

    view = webapp.project_overview(cartoon, KNOWLEDGE)
    assert view["episodes"][0]["fact_check"] is None


def test_panel_block_repeats_the_gate_verbatim(project, monkeypatch):
    """Панель и approve обязаны называть одну причину: два ответа об одном
    состоянии человек прочитает как ошибку панели."""
    from factory import webapp
    monkeypatch.chdir(project.parent)

    view = webapp.project_overview(project, KNOWLEDGE)
    block = view["episodes"][0]["fact_check"]

    # Сравниваем с `report_problem` — тем самым источником, к которому сводится
    # и `preprod.fact_check_problem`, которым отказывает approve. Звать сам
    # `fact_check_problem` здесь нельзя: он читает карточки жанров от текущего
    # каталога, а тест в него и чдирит.
    assert block["passed"] is False
    assert block["problem"] == factcheck.report_problem(project, "ep01")


def test_panel_block_after_a_passed_check(project, monkeypatch):
    from factory import webapp

    factcheck.run(project, REPO, "ep01",
                  engine=FakeEngine([CLAIMS_ANSWER, VERDICT_ANSWER]),
                  search=FakeSearch(), log=lambda *_: None)
    monkeypatch.chdir(project.parent)

    block = webapp.project_overview(project, KNOWLEDGE)["episodes"][0]["fact_check"]
    assert block["passed"] is True
    assert block["verdict"] == "passed"
    assert block["claims"] == 1
    assert block["report"] == "episodes/ep01/fact-check.md"


def test_sources_are_collected_without_duplicates(project):
    report = project / "episodes" / "ep01" / "fact-check.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "---\nkind: fact-check\nstatus: draft\n---\n"
        "NASA — https://nasa.gov/a, ESA — (https://esa.int/b).\n"
        "Снова https://nasa.gov/a\n", encoding="utf-8")

    assert factcheck.report_sources(project, "ep01") == [
        "https://nasa.gov/a", "https://esa.int/b"]


def test_only_http_links_leave_the_report(project):
    """Ссылки пишет модель. `javascript:` в разметке панели — не источник."""
    report = project / "episodes" / "ep01" / "fact-check.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "---\nkind: fact-check\nstatus: draft\n---\n"
        "javascript:alert(1) и data:text/html,x и https://nasa.gov/ok\n",
        encoding="utf-8")

    assert factcheck.report_sources(project, "ep01") == ["https://nasa.gov/ok"]


def test_report_state_of_a_missing_report_is_not_an_error(project):
    state = factcheck.report_state(project, "ep01")

    assert state["exists"] is False
    assert state["passed"] is False
    assert state["sources"] == []


def test_state_message_carries_no_terminal_command(project):
    """У терминала и панели разные лекарства от одной болезни: команда посреди
    панели читалась бы как «иди в другое место», при том что кнопка рядом."""
    assert "python " not in factcheck.report_problem(project, "ep01")
    assert "text_stage" not in factcheck.report_problem(project, "ep01")


def test_cli_refusal_still_names_the_command(project, capsys):
    """CLI обязан сказать, чем чинить: там кнопки нет."""
    import factory_cli_entry as fc
    _bible(project)

    fc.main(["approve", "--project", str(project), "episodes/ep01/script.md"])

    out = capsys.readouterr().out
    assert "text_stage.py" in out and "--stage factcheck" in out
