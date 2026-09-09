"""Проверка фактов познавательного жанра: maker-checker в пустом контексте.

Сценарий пишет один вызов, проверяет ДРУГОЙ — он не видел, как сценарий
сочинялся, и не наследует его уверенности. Пустой контекст выражен данными, а не
обещанием: у стадии `factcheck` во входах стоит один только `script.md`, поэтому
ни идея, ни арка, ни правила ремесла до проверяющего не доезжают.

Методика проверки не переписана сюда: она в `.claude/skills/factory-factcheck/
SKILL.md`, и её тело становится системным промптом. Здесь только доставка —
два прохода, поиск между ними и запись результата.

Почему два прохода: чтобы искать, нужны запросы, а какие утверждения проверять,
решает проверяющий, а не код. Первый проход называет утверждения и запросы,
код ищет, второй проход выносит вердикт по найденному.

Ищет либо код (ключ поиска), либо сам агент (Claude Code умеет искать
инструментами). Развилка одна и объявлена явно: подменять поиск молчанием
нельзя — проверяющий без источников честно напишет «подтверждений не нашлось» и
завалит верный факт.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from factory.artifact import ArtifactError, load_artifact, save_artifact
from factory.genres import GenreError
from factory.project import ProjectError, load_project
from factory.providers import ProviderError, get_search_provider
from factory.safety import is_safe_name
from factory.text import stages as text_stages
from factory.text.engine import TextEngine, TextEngineError

STAGE_ID = "factcheck"
REPORT_NAME = "fact-check.md"

# Потолок поисковых запросов на одну серию. При $0.016 за запрос это $0.64 —
# на фоне съёмки шум, но защита от сценария, в котором проверяющий назовёт две
# сотни утверждений. Утверждения сверх потолка НЕ выбрасываются: они уезжают
# проверяющему помеченными как непроверенные, и он обязан вынести по ним «не
# проверить» — то есть серия падает в `failed`, а не проходит молча.
MAX_SEARCHES = 40

_CLAIM_BLOCK = re.compile(
    r"===\s*CLAIM\s*===\s*(?P<body>.*?)\s*===\s*END CLAIM\s*===",
    re.DOTALL | re.IGNORECASE)
_FIELD = re.compile(r"^\s*(утверждение|запрос)\s*:\s*(?P<value>.+?)\s*$",
                    re.IGNORECASE | re.MULTILINE)
_VERDICT = re.compile(r"===\s*VERDICT:\s*(?P<value>passed|failed)\s*===",
                      re.IGNORECASE)

VERDICTS = ("passed", "failed")


class FactCheckError(ValueError):
    """Проверку не провести или её результат не разобрать."""


class FactCheckBlocked(FactCheckError):
    """Проверять нечего: гейт этапа не пускает.

    Отдельный класс, а не текст ошибки: у отказа гейта и у сорванной проверки
    разная природа и разные коды выхода (2 против 1). Наследование от
    FactCheckError оставлено сознательно — обработчики, ловящие общий тип, не
    начнут пропускать отказ гейта наружу трейсбеком.
    """


# Сколько символов ответа модели показать в ошибке разбора. Без хвоста «в ответе
# нет строки VERDICT» неотличимо от «модель сломалась»: живой прогон 2026-09-09
# кончился именно этим сообщением, а настоящей причиной был отсутствующий
# сценарий — в ответе проверяющий прямо это и написал, но текст никто не увидел.
TAIL_CHARS = 400


def _tail(answer: str) -> str:
    """Хвост ответа модели для сообщения об ошибке."""
    text = (answer or "").strip()
    if not text:
        return "ответ пуст"
    if len(text) > TAIL_CHARS:
        text = "…" + text[-TAIL_CHARS:]
    return f"вот чем он кончился:\n{text}"


@dataclass
class Claim:
    """Одно проверяемое утверждение и запрос, которым его проверяют."""
    text: str
    query: str
    sources: list[dict] | None = None      # None — не искали вовсе
    error: str = ""                        # поиск сорвался — так и скажем


# --- доступность ----------------------------------------------------------

def availability(engine: TextEngine | None = None) -> tuple[bool, str]:
    """Можно ли вообще проверять факты на этой машине и почему нет.

    Два пути, и достаточно любого: ключ поиска (ищет код) или Claude Code
    (ищет агент своими инструментами). Ответ здесь один на всех — его
    показывает панель, его же печатает CLI: два мнения о том, доступен ли жанр,
    это ровно та болезнь, от которой лечит `refs_problems`.
    """
    if engine is not None and getattr(engine, "name", "") == "claude-code":
        return True, ""
    try:
        get_search_provider()
        return True, ""
    except ProviderError as e:
        reason = str(e)

    from factory.text.engine import ClaudeCodeEngine
    if engine is None and ClaudeCodeEngine().available():
        return True, ""
    return False, (
        f"{reason}; и Claude Code не найден в PATH. Проверять факты нечем, "
        "а познавательный жанр без проверки не одобряется")


def genre_requires_check(project_dir: Path | str,
                         knowledge_dir: Path | str = "knowledge") -> bool:
    """Объявил ли жанр проекта обязательную проверку фактов.

    Непрочитанный жанр — не повод требовать проверку: настоящую причину назовут
    гейты, которые смотрят на project.json прицельно. Та же дисциплина, что у
    `genre_stage_problem`.
    """
    try:
        project = load_project(Path(project_dir) / "project.json")
        card = project.genre_card(knowledge_dir)
    except (ProjectError, GenreError, OSError, ValueError):
        return False
    return card.get("fact_check") == "required"


# --- проход 1: утверждения ------------------------------------------------

CLAIMS_TASK = (
    "## Проход 1 из 2: назови утверждения\n\n"
    "Сейчас первый проход. Выпиши проверяемые утверждения сценария блоками "
    "`=== CLAIM === … === END CLAIM ===`, по одному на утверждение, с полями "
    "`утверждение:` и `запрос:` — каждое одной строкой.\n\n"
    "Файлов в этом проходе не пиши: их ждут во втором проходе, когда будет "
    "что проверять.")


def parse_claims(answer: str) -> list[Claim]:
    """Утверждения из ответа первого прохода.

    Пустой список — законный ответ (в сценарии нет проверяемых фактов), поэтому
    исключения здесь нет. А вот блок без одного из полей — ошибка формата:
    утверждение без запроса нечем проверять, и молча его пропустить значит
    выдать непроверенное за проверенное.
    """
    claims: list[Claim] = []
    for block in _CLAIM_BLOCK.finditer(answer or ""):
        fields = {m.group(1).lower(): m.group("value")
                  for m in _FIELD.finditer(block.group("body"))}
        text = (fields.get("утверждение") or "").strip()
        query = (fields.get("запрос") or "").strip()
        if not text or not query:
            raise FactCheckError(
                "в блоке CLAIM нет поля 'утверждение' или 'запрос': "
                + block.group("body").strip()[:TAIL_CHARS])
        claims.append(Claim(text=text, query=query))
    return claims


# --- поиск ----------------------------------------------------------------

def gather(claims: list[Claim], provider, *, max_searches: int = MAX_SEARCHES,
           log=print) -> list[Claim]:
    """Найти источники по каждому утверждению. Сорванный поиск — не молчание.

    Провал одного запроса не роняет проверку целиком: остальные утверждения
    проверить всё ещё можно, а по этому проверяющий увидит причину и вынесет
    «не проверить». Промолчать здесь значило бы выдать сетевую ошибку за
    отсутствие подтверждений.
    """
    for i, claim in enumerate(claims):
        if i >= max_searches:
            break
        try:
            claim.sources = provider.search(claim.query)
        except ProviderError as e:
            claim.sources = []
            claim.error = str(e)
        log(f"  [{i + 1}/{min(len(claims), max_searches)}] "
            f"{claim.query} — "
            + (f"ошибка поиска: {claim.error}" if claim.error
               else f"{len(claim.sources)} источник(ов)"))
    return claims


# --- проход 2: вердикт ----------------------------------------------------

def verdict_task(claims: list[Claim], *, searched: bool) -> str:
    """Задание второго прохода: утверждения и то, что по ним известно."""
    parts = ["## Проход 2 из 2: вердикт", ""]
    if not claims:
        parts.append(
            "В первом проходе проверяемых утверждений не нашлось. Убедись, что "
            "это правда, и вынеси вердикт по серии.")
        return "\n".join(parts)

    parts.append(
        "Ниже утверждения из первого прохода." + (
            " По каждому приложены выдержки из найденного — работай по ним и "
            "не считай источниками пересказы одного и того же."
            if searched else
            " Выдержек нет: ищи сам своими инструментами, по одному запросу на "
            "утверждение, и не сокращай список."))
    parts.append("")

    for i, claim in enumerate(claims, 1):
        parts.append(f"### Утверждение {i}\n")
        parts.append(claim.text)
        parts.append(f"\nПоисковый запрос: `{claim.query}`")
        if claim.sources is None:
            parts.append(
                "\nПоиск по этому утверждению НЕ проводился (превышен потолок "
                f"в {MAX_SEARCHES} запросов на серию). Своими инструментами "
                "проверить его, если умеешь; иначе вердикт — «не проверить».")
        elif claim.error:
            parts.append(f"\nПоиск сорвался: {claim.error}")
        elif not claim.sources:
            parts.append("\nПоиск не дал ни одного результата.")
        else:
            parts.append("")
            for src in claim.sources:
                title = src.get("title") or src["url"]
                parts.append(f"- **{title}** — {src['url']}\n"
                             f"  > {(src.get('snippet') or '').strip()}")
        parts.append("")
    return "\n".join(parts)


def parse_verdict(answer: str) -> str:
    """Вердикт серии из ответа второго прохода.

    Отсутствие вердикта — ошибка, а не «наверное failed» и тем более не
    «наверное passed»: гадать за проверяющего значит подписывать справку,
    которую он не выдавал.
    """
    match = _VERDICT.search(answer or "")
    if not match:
        raise FactCheckError(
            "в ответе нет строки '=== VERDICT: passed ===' или "
            "'=== VERDICT: failed ==='; " + _tail(answer))
    return match.group("value").lower()


# --- запись результата ----------------------------------------------------

def report_rel(episode: str) -> str:
    return f"episodes/{episode}/{REPORT_NAME}"


def script_rel(episode: str) -> str:
    return f"episodes/{episode}/script.md"


def stamp_report(project_dir: Path | str, episode: str, *, verdict: str,
                 claims: int, engine: str, model: str | None) -> str:
    """Проставить в отчёт машинные поля: вердикт и хеш проверенного сценария.

    Хеш обязателен: без него отчёт остаётся годным после правки сценария, и
    «проверено» относилось бы к тексту, которого больше нет. Ту же дисциплину
    несёт `content_sha` у одобренных артефактов.

    Поля ставит КОД, а не модель: справку о прохождении проверки не выдаёт себе
    сам проверяемый.
    """
    project_dir = Path(project_dir)
    if verdict not in VERDICTS:
        raise FactCheckError(f"неизвестный вердикт {verdict!r}; ждали {VERDICTS}")

    path = project_dir / report_rel(episode)
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError) as e:
        raise FactCheckError(f"отчёт проверки не читается: {e}") from None

    script = project_dir / script_rel(episode)
    try:
        script_sha = load_artifact(script).sha
    except (ArtifactError, OSError) as e:
        raise FactCheckError(f"сценарий не читается: {e}") from None

    art.meta["kind"] = "fact-check"
    art.meta["status"] = "draft"
    art.meta["verdict"] = verdict
    art.meta["script_sha"] = script_sha
    art.meta["claims"] = claims
    art.meta["engine"] = engine
    art.meta["model"] = model or ""
    art.meta["checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds")
    save_artifact(art)
    return script_sha


def report_problem(project_dir: Path | str, episode: str) -> str | None:
    """Что не так с проверкой фактов этой серии; None — проверка пройдена.

    ЕДИНСТВЕННЫЙ источник вердикта о проверке: его читают `factory.py approve`,
    гейты этапов и панель. Заводить копию нельзя — три команды с тремя мнениями
    об одном состоянии проекта это уже пройденная болезнь (D-3).

    Здесь только СОСТОЯНИЕ, без «что делать»: у терминала и у панели разные
    лекарства от одной болезни. Панель ставит рядом кнопку, CLI печатает
    команду (`factory.py approve`), и совет из терминала посреди панели читался
    бы как «иди в другое место» — при том что кнопка рядом.
    """
    project_dir = Path(project_dir)
    rel = report_rel(episode)
    path = project_dir / rel
    if not path.exists():
        return f"{rel}: проверки фактов не было"
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError) as e:
        return f"{rel}: отчёт проверки не читается — {e}"

    verdict = art.meta.get("verdict")
    if verdict != "passed":
        return (f"{rel}: проверка фактов не пройдена (verdict: "
                f"{verdict or 'нет поля'}) — почини сценарий и проверь заново")

    script = project_dir / script_rel(episode)
    try:
        current = load_artifact(script).sha
    except (ArtifactError, OSError) as e:
        return f"{script_rel(episode)}: не читается — {e}"
    if art.meta.get("script_sha") != current:
        return (f"{rel}: проверка относится к другой версии сценария — "
                "сценарий правили после неё, проверь заново")
    return None


# Ссылки из отчёта. Их пишет ПРОВЕРЯЮЩИЙ, то есть модель, поэтому наружу уходят
# только http(s): `javascript:` в разметке панели — не источник, а способ
# выполнить чужой код в окне, у которого есть доступ ко всем проектам.
_LINK = re.compile(r"https?://[^\s)>\]\"']+")


def report_sources(project_dir: Path | str, episode: str) -> list[str]:
    """Ссылки, найденные в отчёте проверки, по одной и без повторов.

    Отчёт — свободная проза: проверяющему велено дать перечень источников, но
    формы у него нет. Поэтому здесь честное «ссылки, которые в отчёте есть», а
    не выдуманная структура, которой модель не обещала.
    """
    try:
        body = load_artifact(Path(project_dir) / report_rel(episode)).body
    except (ArtifactError, OSError):
        return []
    found: list[str] = []
    for url in _LINK.findall(body):
        url = url.rstrip(".,;:")
        if url not in found:
            found.append(url)
    return found


def report_state(project_dir: Path | str, episode: str) -> dict:
    """Всё о проверке этой серии одним словарём — для панели.

    Вердикт берётся у `report_problem`, а не считается заново: панель обязана
    говорить ровно то, что скажет `approve`, отказываясь одобрять сценарий.
    """
    project_dir = Path(project_dir)
    path = project_dir / report_rel(episode)
    problem = report_problem(project_dir, episode)
    meta: dict = {}
    if path.exists():
        try:
            meta = load_artifact(path).meta or {}
        except (ArtifactError, OSError):
            meta = {}
    return {
        "exists": path.exists(),
        "passed": problem is None,
        "problem": problem or "",
        "verdict": meta.get("verdict") or "",
        "claims": meta.get("claims"),
        "checked_at": meta.get("checked_at") or "",
        "engine": meta.get("engine") or "",
        "model": meta.get("model") or "",
        "report": report_rel(episode),
        "sources": report_sources(project_dir, episode),
    }


# --- оркестровка ----------------------------------------------------------

def run(project_dir: Path | str, repo_root: Path | str, episode: str, *,
        engine: TextEngine, model: str | None = None, search=None,
        log=print) -> dict:
    """Провести проверку целиком: два прохода, поиск между ними, запись.

    Один вход для CLI и для панели: методика проверки не должна зависеть от
    того, откуда её позвали.
    """
    if not is_safe_name(episode):
        raise FactCheckError(f"недопустимое имя серии: {episode!r}")
    project_dir = Path(project_dir)

    # Гейт стоит ЗДЕСЬ, а не в точках входа: путей запуска два (CLI и панель), и
    # проверка, скопированная в оба, однажды достанется только одному. Так уже
    # было: гейт `_fact_check_stage_problems` существовал с самого начала, но
    # звали его только `factory.py check` — а панель пускала проверку на серию
    # без сценария, и проверяющий честно отказывался выносить вердикт по
    # пустоте. Человек читал это как поломку движка.
    from factory.preprod import fact_check_input_problems

    blockers = fact_check_input_problems(project_dir, episode)
    if blockers:
        raise FactCheckBlocked("; ".join(blockers))

    # Готовый провайдер поиска в аргументе — сам себе доказательство
    # доступности; спрашивать после этого «а есть ли чем искать» незачем.
    if search is None:
        ok, reason = availability(engine)
        if not ok:
            raise FactCheckError(reason)
        try:
            search = get_search_provider()
        except ProviderError as e:
            # Ключа нет — значит ищет агент. До сюда доходит только тот движок,
            # который это умеет: остальных отбила availability выше.
            log(f"поиск кодом недоступен ({e}); ищет сам агент")
            search = None

    # --- проход 1
    log("проход 1: какие утверждения проверять")
    try:
        first = text_stages.build_prompt(
            STAGE_ID, project_dir, repo_root, episode=episode, extra=CLAIMS_TASK)
    except text_stages.StageError as e:
        raise FactCheckError(str(e)) from None
    try:
        answer = engine.complete(first.system, first.user, model=model)
    except TextEngineError as e:
        raise FactCheckError(str(e)) from None
    claims = parse_claims(answer)
    log(f"утверждений: {len(claims)}")

    # --- поиск
    if search is not None and claims:
        log(f"поиск через {search.name}")
        gather(claims, search, log=log)
        if len(claims) > MAX_SEARCHES:
            log(f"утверждений больше потолка ({MAX_SEARCHES}): остальные уйдут "
                "проверяющему непроверенными")

    # --- проход 2
    log("проход 2: вердикт")
    try:
        second = text_stages.build_prompt(
            STAGE_ID, project_dir, repo_root, episode=episode,
            extra=verdict_task(claims, searched=search is not None))
    except text_stages.StageError as e:
        raise FactCheckError(str(e)) from None
    try:
        answer = engine.complete(second.system, second.user, model=model)
    except TextEngineError as e:
        raise FactCheckError(str(e)) from None

    verdict = parse_verdict(answer)
    try:
        files = text_stages.parse_files(answer)
        written = text_stages.write_files(
            STAGE_ID, project_dir, files, episode=episode)
    except text_stages.StageError as e:
        raise FactCheckError(str(e)) from None

    if report_rel(episode) not in written:
        raise FactCheckError(
            f"проверяющий не отдал {report_rel(episode)} — вердикт без отчёта "
            "не документ")

    script_sha = stamp_report(project_dir, episode, verdict=verdict,
                              claims=len(claims), engine=engine.name, model=model)
    return {"verdict": verdict, "claims": len(claims), "written": written,
            "script_sha": script_sha, "answer": answer,
            "search": getattr(search, "name", None)}
