"""Состояние артефактов и гейты первой половины конвейера (спека 2026-08-02 §5).

Одобрение живёт во frontmatter артефакта вместе с хешом тела и хешами зависимостей,
поэтому правка утверждённого текста не проходит молча.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from factory.artifact import (Artifact, ArtifactError, body_sha, has_canonical,
                              load_artifact, split_frontmatter)
from factory.manifest import Manifest, ManifestError
from factory.project import ProjectError, load_project
from factory.safety import is_safe_name  # noqa: F401  (реэкспорт: проверка живёт в safety.py, зовут её отсюда исторически)

# Карта зависимостей по kind — фиксированная, а не свободный список: иначе два
# запуска approve дали бы разный depends_on и проверка устаревания стала бы
# недетерминированной (спека §4).
DEPENDS_ON: dict[str, list[str]] = {
    "research": [],
    "idea": [],
    "season-arc": ["bible/idea.md"],
    "style-guide": ["bible/idea.md"],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "character": ["bible/idea.md", "bible/style-guide.md"],
}


def _script_cast(script: Path) -> list[str]:
    """Состав серии — из объявленного поля characters во frontmatter сценария.

    Состав ОБЪЯВЛЯЕТСЯ явно, а не ищется по тексту. Поиск имени подстрокой врёт в обе
    стороны: «Мурзик смотрит на фотографию Барсика» записал бы Барсика в участники
    сцены, а персонажа, названного в сценарии иначе, не нашёл бы вовсе. Тот же ход уже
    принят в спеке §10 для промптов кадров ({{char:...}} вместо поиска имени).

    Сценарий без поля characters — пустой состав: серия без персонажей технически
    возможна (заставка, титры). Битый сценарий пропускаем: его отобьёт гейт
    собственного этапа, ронять здесь нечем.
    """
    try:
        declared = load_artifact(script).meta.get("characters") or []
    except (ArtifactError, OSError):
        return []
    return [str(name) for name in declared]


def unsafe_names(project_dir: Path, episode: str) -> list[str]:
    """Имена состава серии, непригодные как имя файла."""
    return [n for n in episode_cast(project_dir, episode) if not is_safe_name(n)]


def episode_cast(project_dir: Path, episode: str) -> list[str]:
    """Персонажи, объявленные в сценарии эпизода."""
    return _script_cast(Path(project_dir) / "episodes" / episode / "script.md")


def dependencies(project_dir: Path, art: Artifact) -> list[Path]:
    """Файлы, от которых артефакт зависит. Для персонажа к статическому списку
    добавляются сценарии, объявившие его в своём составе: правка такого сценария
    меняет то, каким персонаж должен быть.

    Список статических путей отдаётся как есть, даже если файл ещё не создан:
    это ожидаемые зависимости по карте DEPENDS_ON, а не проверка «что уже готово».
    Отфильтровывать несуществующее тут не нужно и вредно — например, approve
    сценария должен видеть bible/idea.md среди его зависимостей независимо от
    порядка, в котором артефакты создаются."""
    project_dir = Path(project_dir)
    kind = art.meta.get("kind")
    deps = [project_dir / rel for rel in DEPENDS_ON.get(kind, [])]
    if kind == "character":
        name = art.meta.get("name") or art.path.stem
        for script in sorted((project_dir / "episodes").glob("*/script.md")):
            if name in _script_cast(script):
                deps.append(script)
    return deps


def artifact_state(project_dir: Path, path: Path) -> str:
    """missing | broken | draft | approved | stale_self | stale_deps.

    `broken` — файл есть, но не читается (битый frontmatter, каталог вместо файла).
    Отдельное состояние нужно ради формулировки: сказать про такой файл «не одобрен
    (status: draft)» значит послать человека одобрять то, что не разбирается. Гейт
    трактует его как всякое не-approved, но сообщение даёт другое.

    Нечитаемая ЗАВИСИМОСТЬ — это по-прежнему `stale_deps`, а не `broken`: там речь
    не про этот файл, а про то, что его основание невозможно подтвердить.
    """
    project_dir, path = Path(project_dir), Path(path)
    if not path.exists():
        return "missing"
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError):
        return "broken"
    if art.meta.get("status") != "approved":
        return "draft"
    if art.meta.get("content_sha") != art.sha:
        return "stale_self"
    for dep in art.meta.get("depends_on") or []:
        if _dep_problem(project_dir, dep):
            return "stale_deps"
    return "approved"


def _dep_problem(project_dir: Path, dep: dict) -> str | None:
    """Что не так с одной объявленной зависимостью; None — всё в порядке.

    Общая для `artifact_state` (её интересует только факт) и `stale_reason` (ей
    нужна формулировка). Разделять их значило бы держать два описания одного
    правила и однажды разойтись.
    """
    dep_path = Path(project_dir) / dep["path"]
    rel = dep["path"]
    # Зависимость обязана лежать ВНУТРИ проекта. Путь берётся из frontmatter,
    # то есть из данных: '../../чужое.md' иначе читался бы и хешировался, и
    # артефакт объявлялся approved на основании файла вне проекта
    # (воспроизведено ревью 2026-08-02).
    try:
        inside = dep_path.resolve().is_relative_to(Path(project_dir).resolve())
    except OSError:
        inside = False
    if not inside:
        return f"{rel}: зависимость ведёт наружу проекта"
    if not dep_path.exists():
        return f"{rel}: зависимость удалена"
    try:
        dep_sha = load_artifact(dep_path).sha
    except (ArtifactError, OSError):
        # Зависимость есть на диске, но не разбирается (битый/чужой frontmatter) —
        # у контракта artifact_state нет состояния "ошибка", а подтвердить, что
        # основание не изменилось, мы не можем. Значит не вправе звать это
        # approved: та же логика, что и для удалённой зависимости выше, поэтому
        # тот же исход — stale_deps, а не отдельное "broken".
        return f"{rel}: зависимость не читается"
    if dep_sha != dep["sha"]:
        return f"{rel}: зависимость изменилась"
    return None


def stale_reason(project_dir: Path, path: Path) -> str:
    """Какая именно зависимость сделала артефакт устаревшим.

    Спека §5 обосновывает отдельное состояние `stale_deps` тем, что человек должен
    понять, ЧЕЙ файл перечитывать. Одно сообщение на «изменилась», «удалена» и «не
    разбирается» говорило ему только, что виноват чужой файл.
    """
    project_dir, path = Path(project_dir), Path(path)
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError):
        return "зависимости не проверить: артефакт не читается"
    for dep in art.meta.get("depends_on") or []:
        problem = _dep_problem(project_dir, dep)
        if problem:
            return problem
    return "зависимости в порядке"


STAGES = ("research", "story", "script", "characters", "storyboard",
          "audio_plan")

# Правила ремесла — четвёртый выход этапа story и единственный его выход, у
# которого нет статуса: `craft-notes.md` не одобряют, его читают. Поэтому в
# STAGE_REQUIRES он не выражается, а закрытость этапа считается отдельно:
# файл есть и в нём что-то написано. Без этого story считался закрытым по трём
# одобренным артефактам, а стадия молча не писала четвёртый — и весь конвейер
# ехал без границ из брифа (живой прогон 2026-09-09).
CRAFT_NOTES = "bible/craft-notes.md"

# Проверка фактов стоит особняком от STAGES, и это не оплошность: её вход —
# сценарий, который ещё НЕ одобрен и до неё одобрен быть не может. Через
# STAGE_REQUIRES (там перечислено одобренное) это не выражается вовсе, а
# записать её туда с пустыми требованиями значило бы соврать про порядок.
FACT_CHECK_STAGE = "factcheck"

# Платные стадии: их гейты живут в generate_batch/render, но спрашивать про них
# человек должен той же командой. Пока `check` знала только пре-продакшн, ответ
# «известны research…storyboard» выглядел так, будто отрезков в конвейере нет.
PAID_STAGES = ("storyboard_generate", "segments", "audio", "foley", "lipsync",
               "render")

# Имя стадии у резолвера и имя, которым её запускают, совпадают везде, кроме
# кадров: резолверу нужно отличать текстовый этап `storyboard` (пишет
# shots.json) от платной генерации кадров, а CLI знает вторую как
# `--stage storyboard`. Перевод живёт ЗДЕСЬ и только здесь: панель отправляла
# в запуск имя резолвера как есть и получала «неизвестная стадия», то есть
# конвейер вставал на первом же платном шаге (найдено ревью 2026-09-09).
_RUN_NAME = {"storyboard_generate": "storyboard"}


def cli_stage(stage: str) -> str:
    """Имя стадии, которым её запускают CLI и панель."""
    return _RUN_NAME.get(stage, stage)

# Человеческие имена стадий: машинное `storyboard_generate` в сообщении гейта
# ничего не объясняет тому, кто спрашивает «почему нельзя».
STAGE_LABELS = {
    "audio_plan": "план звука",
    "storyboard_generate": "генерация кадров раскадровки",
    "segments": "генерация видеоотрезков",
    "audio": "озвучка, музыка и эффекты",
    "foley": "дорожки фактуры по отрезкам",
    "lipsync": "синхронизация губ",
    "render": "монтаж эпизода",
}

# Что каждый этап требует одобренным. {ep} подставляется номером эпизода.
STAGE_REQUIRES: dict[str, list[str]] = {
    "research": [],
    "story": [],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "characters": ["episodes/{ep}/script.md"],
    "storyboard": ["episodes/{ep}/script.md", "bible/style-guide.md"],
    # План звука пишется по одобренному сценарию: реплики берутся оттуда
    # дословно. Раскадровка ему тоже нужна — но не одобрением, а файлом
    # (shots.json без frontmatter), поэтому она проверяется отдельно.
    "audio_plan": ["episodes/{ep}/script.md"],
}


def artifact_written(path: Path) -> bool:
    """Написан ли артефакт по существу, а не только создан скаффолдом.

    Пустой `script.md` тоже `draft`, но одобрять в нём нечего — и ждать
    человека он не должен. Тот же вопрос задаёт `factory.py approve`, отказывая
    «тело пустое — нечего одобрять»; спрашивают его двое (резолвер и панель),
    поэтому ответ здесь один.
    """
    try:
        return bool(load_artifact(Path(path)).body.strip())
    except (ArtifactError, OSError):
        return False


def craft_notes_problem(project_dir: Path) -> str | None:
    """Написаны ли правила ремесла проекта; None — написаны.

    Пустое тело не считается написанным: скаффолд создаёт файлы заранее, и
    «файл существует» означало бы, что этап сделан, ещё до того, как его вели.
    """
    path = Path(project_dir) / CRAFT_NOTES
    if not path.exists():
        return f"{CRAFT_NOTES}: не написан — правила ремесла читает каждая " \
               "творческая стадия"
    try:
        body = load_artifact(path).body
    except (ArtifactError, OSError):
        body = ""
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            pass
    if not body.strip():
        return f"{CRAFT_NOTES}: пуст — правила ремесла читает каждая " \
               "творческая стадия"
    return None

_STATE_MESSAGE = {
    "missing": "не существует",
    "broken": "не читается: битый frontmatter — почини файл, одобрять нечего",
    "draft": "не одобрен (status: draft)",
    "stale_self": "изменён после одобрения — перечитай и одобри заново",
    "stale_deps": "устарел: изменился файл, на который он опирался",
}


def _state_message(project_dir: Path, path: Path, state: str) -> str:
    """Сообщение гейта о состоянии артефакта, с виновником для stale_deps."""
    if state != "stale_deps":
        return _STATE_MESSAGE[state]
    return f"устарел — {stale_reason(project_dir, path)}"


def episode_ids(project_dir: Path) -> list[str]:
    """ep01..epNN по полю episodes из project.json; для типов без серий — ['ep01']."""
    data = json.loads((Path(project_dir) / "project.json").read_text(encoding="utf-8"))
    # Было `int(data.get("episodes", 1) or 1)`: ноль молча превращался в одну серию,
    # отрицательное — в пустой список, из-за чего next_stage объявлял «всё закрыто»
    # на пустом проекте. Внятный отказ честнее тихой подстановки.
    raw = data.get("episodes", 1)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        raise ProjectError(
            f"episodes должно быть числом, получено {raw!r}") from None
    if count < 1:
        raise ProjectError(f"episodes должно быть >= 1, получено {count}")
    return [f"ep{i:02d}" for i in range(1, count + 1)]


ACCEPTED_REF = {"done", "accepted_with_notes"}


def refs_problems(project_dir: Path, episode: str, *,
                  require_accepted: bool = True) -> list[str]:
    """По строке на каждого персонажа серии, чей референс нельзя использовать.

    Единственный источник вердикта о референсах: его читают и `stage_gate`
    (а значит `factory.py check`), и `next_stage`, и платная стадия storyboard в
    generate_batch.py. Раньше проверка жила только в generate_batch.py, а
    резолвер имел свою половинчатую копию — три команды отвечали про одно
    состояние по-разному (D-3 первого живого прогона).

    Нужен резолверу: этап characters состоит из двух половин — тексты карточек и
    платная генерация референсов. Считать этап закрытым по одним лишь одобренным
    текстам значит никогда не позвать вторую половину: драйвер уходил бы в
    storyboard и упирался там в код 3 на каждом эпизоде (находка финального ревью).

    ``require_accepted=False`` — вопрос САМОГО этапа characters: непринятый
    референс ему не мешает (он его и производит), а вот принятый, но устаревший
    мешает — этап его не перегенерирует (``manifest.add`` идемпотентен, `done` в
    `pending` не возвращается), и без этой ветки стадия молча отвечала бы «нечего
    делать» кодом 0, а резолвер звал бы её снова и снова.
    """
    project_dir = Path(project_dir)
    manifest_path = project_dir / "manifest.json"
    manifest = Manifest(manifest_path) if manifest_path.exists() else None
    problems = []
    for name in episode_cast(project_dir, episode):
        item_id = f"bible/characters/{name}"
        item = None
        if manifest is not None:
            try:
                item = manifest.get(item_id)
            except ManifestError:
                item = None
        if item is None:
            if require_accepted:
                problems.append(f"{item_id}: референс не генерировался")
            continue
        if item["status"] not in ACCEPTED_REF:
            if require_accepted:
                problems.append(f"{item_id}: референс в статусе {item['status']}")
            continue
        # Референс принят, но карточка могла измениться после приёмки (находка
        # ревью 2026-08-02): кадры пошли бы по описанию, которого уже нет.
        # card_sha отсутствует у манифестов, записанных до той правки, — старые
        # проекты не блокируем задним числом.
        stored = item.get("card_sha")
        if not stored:
            continue
        try:
            current = load_artifact(
                project_dir / "bible" / "characters" / f"{name}.md").sha
        except (ArtifactError, OSError):
            # Карточку не прочитать — про это говорит _cast_problems, здесь
            # сравнивать нечего; без одобренной карточки этап всё равно закрыт.
            continue
        if stored != current:
            problems.append(
                f"{item_id}: карточка изменилась после приёмки референса — "
                "перегенерируй референс (review.py requeue)")
    return problems


def _paid_stage_problems(project_dir: Path, stage: str,
                         episode: str | None) -> list[str]:
    """Что мешает начать платную стадию. Пустой список — можно.

    Считается по тем же примитивам, что и `_paid_stage`: собственного гейта у
    `check` нет, иначе появился бы четвёртый ответ на тот же вопрос (D-3 первого
    живого прогона — три команды давали три разных ответа про одно состояние).
    """
    if episode is None:
        return [f"этап {stage} требует --episode"]
    episode_dir = Path(project_dir) / "episodes" / episode
    if not (episode_dir / "shots.json").exists():
        return [f"нет {episode_dir / 'shots.json'} — сначала этап storyboard"]
    if (stage in ("audio", "foley", "lipsync")
            and not (episode_dir / "audio.json").exists()):
        return [f"нет {episode_dir / 'audio.json'} — сначала /factory-audio"]
    pending = _paid_stage(project_dir, episode)
    if pending == stage:
        return []
    if pending is None:
        return [f"по эпизоду {episode} платных работ не осталось "
                f"(следующая стадия: нет)"]
    label = STAGE_LABELS.get(pending, pending)
    return [f"сейчас очередь стадии {pending!r} ({label}), а не {stage!r}"]


def genre_stage_problem(project_dir: Path, stage: str) -> str | None:
    """Существует ли стадия у жанра проекта.

    Отдельная функция, потому что спрашивают трое: гейт этапа, платный гейт и
    панель. Разные ответы на этот вопрос дали бы ровно ту болезнь, от которой
    лечит `refs_problems`, — три команды с тремя мнениями об одном состоянии.

    Непрочитанный жанр — не повод блокировать: карточки жанров могут быть
    недоступны (запуск не из корня), а настоящую причину назовут проверки ниже.
    """
    from factory.genres import GenreError, stage_allowed

    try:
        project = load_project(Path(project_dir) / "project.json")
        card = project.genre_card()
    except (ProjectError, GenreError, OSError):
        return None

    if not stage_allowed(card, stage):
        return (f"этап {stage!r} не существует у жанра {card['id']!r} "
                f"({card['label']}): стадии жанра — {card['stages']}"
                + ("; липсинк недоступен: губ в кадре нет" if stage == "lipsync" else ""))
    return None


def fact_check_problem(project_dir: Path, episode: str) -> str | None:
    """Что мешает считать факты серии проверенными; None — проверка пройдена.

    ЕДИНСТВЕННЫЙ источник этого вердикта для всего конвейера: его читают
    `factory.py approve` (одобрять непроверенный сценарий нельзя), гейты этапов
    и панель. Копий не заводить — три команды с тремя мнениями об одном
    состоянии проекта уже были болезнью (D-3), и лечится она так же, как у
    `refs_problems`.

    У жанра без `fact_check: required` проблем нет по определению: мультфильму
    проверять нечего, и требовать от него отчёт значило бы выдумать работу.
    """
    from factory.text.factcheck import genre_requires_check, report_problem

    if not genre_requires_check(project_dir):
        return None
    return report_problem(project_dir, episode)


def fact_check_input_problems(project_dir: Path,
                              episode: str | None) -> list[str]:
    """Чего не хватает, чтобы проверке было о чём выносить вердикт.

    Отделено от гейта этапа, потому что спрашивают об этом ДВОЕ и с разных
    сторон: гейт этапа складывает это с доступностью поиска и с работой самого
    этапа, а `factcheck.run` — единственный вход обоих путей запуска — берёт
    отсюда только вопрос «есть ли что проверять». Движок и поиск на том пути
    уже выбраны, спрашивать о них второй раз нечего.

    Разделение не заводит второго мнения: список тут один, и `stage_problems`
    начинается ровно с него.
    """
    from factory.text.factcheck import genre_requires_check

    if episode is None:
        return [f"этап {FACT_CHECK_STAGE} требует --episode"]
    if not genre_requires_check(project_dir):
        return [f"этап {FACT_CHECK_STAGE!r} не существует у этого жанра: "
                "проверка фактов объявляется карточкой жанра "
                "(fact_check: required)"]

    script = project_dir / "episodes" / episode / "script.md"
    state = artifact_state(project_dir, script)
    if state in ("missing", "broken"):
        return [f"episodes/{episode}/script.md: "
                f"{_state_message(project_dir, script, state)} — "
                "проверять нечего, сначала этап script"]
    return []


def _fact_check_stage_problems(project_dir: Path,
                               episode: str | None) -> tuple[list[str], list[str]]:
    """Гейт самой проверки: (блокеры, работа этапа).

    Блокер здесь — то, чего проверка сделать не может: нет серии, нет сценария,
    жанр её не требует, искать нечем. Собственная работа — единственная строка
    от `fact_check_problem`: провести проверку и есть предмет этапа.
    """
    from factory.text.factcheck import availability

    blockers = fact_check_input_problems(project_dir, episode)
    if blockers:
        return blockers, []

    ok, reason = availability()
    if not ok:
        return [reason], []

    problem = fact_check_problem(project_dir, episode)
    return [], [problem] if problem else []


def stage_problems(project_dir: Path, stage: str,
                   episode: str | None = None) -> tuple[list[str], list[str]]:
    """(что мешает извне, что этап ещё не сделал сам).

    Один и тот же список причин отвечает на два РАЗНЫХ вопроса у разных
    потребителей. `stage_gate` — вопрос платной стадии (`generate_batch.py`)
    «можно ли тратить» — ей нужно всё вместе, включая недописанную работу
    самого этапа: по карточке, которой никто не написал, референс не
    сгенерировать. (`next_stage` эту функцию не зовёт: он собирает свой гейт
    из тех же примитивов, `_cast_problems`/`refs_problems`, напрямую — см.
    `next_stage` ниже.) `factory.py check` спрашивает человека «можно ли
    САДИТЬСЯ за этап» — и тут «карточка не существует» на этапе characters
    означает «садись и пиши», а не «стоп»: карточки состава серии этап
    characters сам и производит (находка U-11 первого живого прогона).

    Только у characters есть own_work (свои `_cast_problems` и
    `refs_problems(require_accepted=False)` — обе описывают то, что должен
    сделать САМ этап). У storyboard own_work всегда пуст: карточки и референсы
    для него — выход ПРЕДЫДУЩЕГО этапа, то есть чужой вход, и «не существует»
    там означает настоящий блокер. У всех остальных этапов own_work тоже пуст.

    Непригодный project.json и неизвестный этап — блокеры, возвращаются сразу.
    """
    project_dir = Path(project_dir)

    # Жанр решает, какие стадии вообще существуют: у познавательного нет
    # персонажей, а значит нет ни стадии characters, ни липсинка.
    absent = genre_stage_problem(project_dir, stage)
    if absent:
        return [absent], []

    if stage == FACT_CHECK_STAGE:
        return _fact_check_stage_problems(project_dir, episode)
    if stage in PAID_STAGES:
        return _paid_stage_problems(project_dir, stage, episode), []
    if stage not in STAGES:
        return ([f"неизвестный этап {stage!r}; известны "
                 f"{list(STAGES) + [FACT_CHECK_STAGE] + list(PAID_STAGES)}"], [])

    # Спека §5 требует валидный project.json уже для этапа story, но гейт не смотрел
    # на него вовсе — CLI проверял лишь существование файла. Битый бриф обнаруживался
    # на generate_batch, то есть после того, как написаны идея, арка и стайл-гайд.
    # Проверка стоит для ВСЕХ этапов, а не только для story: из project.json растут и
    # состав эпизодов, и выбор провайдера — гейт, отвечающий «можно» на непригодном
    # брифе, врёт одинаково на любом этапе.
    try:
        load_project(project_dir / "project.json")
    except (ProjectError, OSError) as e:
        return [f"project.json: {e}"], []

    blockers: list[str] = []
    own_work: list[str] = []

    # Проверка фактов — половина работы этапа script у жанра, который её
    # требует: сценарий написан, но одобрить его нельзя, пока факты не сверены.
    # Для этапов, живущих НА одобренном сценарии, та же строка — блокер: она
    # объясняет, почему `approve` откажет, вместо глухого «не одобрен».
    if stage in ("script", "characters", "storyboard") and episode is not None:
        fact_problem = fact_check_problem(project_dir, episode)
        if fact_problem:
            (own_work if stage == "script" else blockers).append(fact_problem)

    # Правила ремесла — работа САМОГО этапа story: он их и пишет. На вопрос
    # «можно ли садиться за этап» ответ от этого не меняется (U-11), но
    # незакрытый выход обязан быть назван, иначе он и дальше остаётся
    # невидимым.
    if stage == "story":
        problem = craft_notes_problem(project_dir)
        if problem:
            own_work.append(problem)

    # Раскадровка нужна плану звука файлом, а не одобрением: реплики
    # привязываются к её единицам (отрезкам, а в режиме кадров — кадрам), и без
    # неё валидатор плана не с чем сверять номера.
    if stage == "audio_plan" and episode is not None:
        shots = project_dir / "episodes" / episode / "shots.json"
        if not shots.exists():
            blockers.append(
                f"нет episodes/{episode}/shots.json — сначала этап storyboard")

    for template in STAGE_REQUIRES[stage]:
        if "{ep}" in template and episode is None:
            blockers.append(f"этап {stage} требует --episode")
            continue
        rel = template.format(ep=episode)
        state = artifact_state(project_dir, project_dir / rel)
        if state != "approved":
            blockers.append(
                f"{rel}: {_state_message(project_dir, project_dir / rel, state)}")

    # Персонажи проверяются ПО СОСТАВУ СЕРИИ, а не по тому, какие карточки уже лежат
    # в bible/characters/. Иначе персонаж, впервые появившийся во второй серии,
    # проходил бы гейт насквозь: карточки первой серии одобрены, значит «всё готово»,
    # и кадры второй уходили бы в платную генерацию без описания и референса нового
    # героя (находка ревью задачи 3).
    cast_problems: list[str] = []
    if stage in ("characters", "storyboard") and episode is not None:
        cast_problems = _cast_problems(project_dir, episode)
        # Небезопасное имя чинится правкой уже одобренного episodes/{ep}/script.md —
        # артефакта ПРЕДЫДУЩЕГО этапа, а не карточки, которую пишет сам characters.
        # Настоящий блокер, а не своя работа этапа, даже там, где own_work — обычный
        # адресат cast_problems: иначе check отвечал бы «этап можно вести» на
        # состояние, которое сам этап разрешить не может — зеркало обмана U-11
        # (находка ревью).
        unsafe = [p for p in cast_problems if _UNSAFE_NAME_MARKER in p]
        blockers.extend(unsafe)
        cast_problems = [p for p in cast_problems if p not in unsafe]
        (own_work if stage == "characters" else blockers).extend(cast_problems)

    # Раскадровка опирается на ПРИНЯТЫЙ ревью референс каждого персонажа серии —
    # то же предусловие, которое проверяет платная стадия. Без этой строки
    # `factory.py check` отвечал «гейт открыт» там, где запуск невозможен (D-3).
    # Этапу characters непринятый референс не мешает — он его и производит; мешает
    # только устаревший (require_accepted=False, см. refs_problems).
    #
    # Спрашиваем только когда тексты состава в порядке: у персонажа без одобренной
    # карточки «референс не генерировался» — не отдельная проблема, а следствие, и
    # человек получал бы по две строки на каждого. Та же дисциплина, что внутри
    # _cast_problems: называем первую блокирующую причину, а не её последствия.
    if stage in ("characters", "storyboard") and episode is not None \
            and not cast_problems:
        refs = refs_problems(project_dir, episode,
                             require_accepted=(stage == "storyboard"))
        (own_work if stage == "characters" else blockers).extend(refs)

    # Симметрично проверке canonical:appearance у персонажей: без блока
    # canonical:style разворачивать {{style}} нечем, и expand_prompt упал бы
    # трейсбеком уже на платной стадии, а не гейтом до сметы. Это про
    # bible/style-guide.md — вход этапа storyboard, а не его собственная работа.
    if stage == "storyboard":
        guide = project_dir / "bible" / "style-guide.md"
        if artifact_state(project_dir, guide) == "approved" \
                and not has_canonical(guide, "style"):
            blockers.append(
                "bible/style-guide.md: нет блока <!-- canonical:style --> — "
                "промпт кадра нечем разворачивать")
    return blockers, own_work


def stage_gate(project_dir: Path, stage: str, episode: str | None = None) -> list[str]:
    """Пустой список = этап можно запускать. Иначе — по строке на каждую причину.

    Публичный контракт для платной стадии (`generate_batch.py`): ей важно ВСЁ
    вместе, деление на блокеры и работу самого этапа её не касается — это
    выражено через `stage_problems`, а не отдельная логика. `next_stage` эту
    функцию не зовёт — он строит свой гейт из тех же примитивов
    (`_cast_problems`/`refs_problems`) напрямую.
    """
    blockers, own_work = stage_problems(project_dir, stage, episode)
    return blockers + own_work


# Общий кусок сообщения о небезопасном имени — единственное место, где он
# формулируется. `_cast_problems` строит из него полную строку, `stage_problems`
# тем же маркером узнаёт свои же строки в готовом списке, чтобы развести их по
# блокерам, не заводя вторую копию проверки `is_safe_name`.
_UNSAFE_NAME_MARKER = "имя не годится как имя файла"


def _cast_problems(project_dir: Path, episode: str) -> list[str]:
    """По строке на каждого персонажа серии, у которого нет одобренной карточки."""
    problems = []
    for name in episode_cast(project_dir, episode):
        if not is_safe_name(name):
            problems.append(
                f"персонаж {name!r}: {_UNSAFE_NAME_MARKER} — уберите "
                "разделители пути и точки-родители")
            continue
        card = project_dir / "bible" / "characters" / f"{name}.md"
        rel = card.relative_to(project_dir).as_posix()
        state = artifact_state(project_dir, card)
        if state != "approved":
            problems.append(f"{rel} (персонаж {name}): "
                            f"{_state_message(project_dir, card, state)}")
            continue
        # Карточка одобрена, но без канонического блока разворачивать в промпте
        # нечего: build_jobs упал бы трейсбеком вместо внятного кода возврата.
        if not has_canonical(card, "appearance"):
            problems.append(
                f"{rel} (персонаж {name}): нет блока <!-- canonical:appearance --> — "
                "промпт кадра нечем разворачивать")
    return problems


FEEDBACK_STATES = ("none", "pending", "recorded")


def feedback_state(path: Path) -> str:
    """none — оценки не было и правок не было; это «неизвестно», а не «хорошо».
    pending — человек правил, причина не разобрана. recorded — правило записано
    в bible/craft-notes.md (спека §11).

    Файл, которого нет, и файл с битым frontmatter трактуются одинаково — «none»:
    и там, и там оценивать нечего, а про битый файл отдельно сообщает колонка
    artifact_state. Без этой защиты cmd_status падал бы трейсбеком на каждом
    broken-артефакте вместо строки "broken" (регрессия найдена на существующем
    тесте test_status_survives_broken_artifact)."""
    path = Path(path)
    if not path.exists():
        return "none"
    try:
        value = load_artifact(path).meta.get("feedback", "none")
    except (ArtifactError, OSError):
        return "none"
    return value if value in FEEDBACK_STATES else "none"


def refs_awaiting_review(project_dir: Path, episode: str) -> bool:
    """Все нерешённые референсы серии ждут ЧЕЛОВЕКА, а не машину.

    `generated` — единственный статус, в котором драйверу делать нечего: картинка
    получена и оплачена, дальше нужен `review.py accept`. Всё остальное —
    отсутствие в манифесте, `pending`, `rejected`, устаревшая карточка — работа
    для машины, и пропускать её нельзя (иначе платная половина этапа никогда бы
    не звалась — находка финального ревью ветки пре-продакшна).
    """
    project_dir = Path(project_dir)
    manifest_path = project_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = Manifest(manifest_path)
    waiting = False
    for name in episode_cast(project_dir, episode):
        item_id = f"bible/characters/{name}"
        try:
            item = manifest.get(item_id)
        except ManifestError:
            return False
        if item["status"] in ACCEPTED_REF:
            continue
        if item["status"] != "generated":
            return False
        waiting = True
    return waiting


def research_required(project_dir: Path) -> bool:
    """Объявил ли жанр проекта обязательное исследование темы.

    Спрашиваем карточку, а не догадываемся: у познавательного `research` — не
    «по желанию перед идеей», а первая фаза конвейера, потому что утверждение
    без источника там риск претензии к площадке. У повествовательных жанров
    исследование остаётся необязательным.
    """
    from factory.genres import GenreError

    try:
        card = load_project(Path(project_dir) / "project.json").genre_card()
    except (ProjectError, GenreError, OSError, ValueError):
        return False
    return bool(card.get("requires_research"))


def next_stage(project_dir: Path) -> tuple[str, str | None] | None:
    """Первый незакрытый шаг. Порядок: research (там, где жанр его требует),
    story, затем эпизоды ПО ПОРЯДКУ, в каждом script → factcheck → characters →
    storyboard (спека §7: автономный режим идёт по всем)."""
    project_dir = Path(project_dir)

    # Исследование идёт ПЕРЕД идеей: библия познавательного жанра, написанная
    # раньше источников, — это выдумка, которую потом придётся переписывать.
    # У жанров без `requires_research` шаг остаётся вне резолвера: он там не
    # обязателен, и требовать его значило бы придумывать работу.
    if (research_required(project_dir)
            and artifact_state(
                project_dir, project_dir / "research.md") != "approved"):
        return ("research", None)

    # Четвёртый выход этапа — правила ремесла. Одобрения у них нет (их читают,
    # а не утверждают), поэтому спрашиваем отдельно: без них дальше едет
    # конвейер без границ из брифа, и заметить это было нечем.
    story_done = all(
        artifact_state(project_dir, project_dir / rel) == "approved"
        for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md")
    ) and craft_notes_problem(project_dir) is None
    if not story_done:
        return ("story", None)

    # Серии, застрявшие на ожидании ЧЕЛОВЕКА, откладываются, а не замораживают
    # сезон: референс на ревью машина не сдвинет, а текстовая работа следующих
    # серий бесплатна и от предыдущей не зависит (D-7 первого живого прогона —
    # один упавший платный шаг останавливал всю бесплатную работу по сезону).
    # Откладывание — не забывание: если больше делать нечего, возвращаем первую
    # отложенную, а не «всё закрыто».
    deferred: list[tuple[str, str | None]] = []
    for ep in episode_ids(project_dir):
        script = project_dir / f"episodes/{ep}/script.md"
        script_state = artifact_state(project_dir, script)
        if script_state != "approved":
            written = (script_state not in ("missing", "broken")
                       and artifact_written(script))
            # Написанный, но непроверенный сценарий — работа для ПРОВЕРКИ, а не
            # повод переписать его заново. Возвращать здесь "script" значило бы
            # отправить автора сочинять поверх того, что уже сочинено, и
            # проверка не позвалась бы никогда.
            if written and fact_check_problem(project_dir, ep):
                return (FACT_CHECK_STAGE, ep)
            # Написан, факты сверены — дальше ждут ЧЕЛОВЕКА с `approve`, и
            # машине тут делать нечего. Возвращать "script" значило бы
            # переписывать по кругу за токены то, что человек не успел
            # прочитать (найдено живым прогоном 2026-09-09 на автономном
            # режиме). Серия пропускается, а не откладывается: запускать в ней
            # нечего, и следующая серия ждать не должна (D-7).
            if script_state == "draft" and written:
                continue
            return ("script", ep)
        if (genre_stage_problem(project_dir, "characters") is None
                and (_cast_problems(project_dir, ep)
                     or refs_problems(project_dir, ep))):
            if not _cast_problems(project_dir, ep) \
                    and refs_awaiting_review(project_dir, ep):
                deferred.append(("characters", ep))
                continue
            return ("characters", ep)
        # Непригодный план съёмки — работа этапа storyboard, а не повод идти
        # дальше: тот же вердикт выносит `_paid_stage`, и спрашиваем его одной
        # функцией, чтобы два места не разошлись в ответе про один файл.
        if not _shots_usable(project_dir, ep):
            return ("storyboard", ep)
        # План звука — тоже текстовая работа, и идёт в этом же бесплатном
        # проходе. Пока его не звали, серия ехала в съёмку молчаливой, а в
        # режиме кадров ещё и бессмысленной: длительность кадра там задаёт
        # реплика. Пустой план — законный ответ («серия без звука»), поэтому
        # спрашиваем существование файла, а не его содержимое.
        if not (project_dir / "episodes" / ep / "audio.json").exists():
            return ("audio_plan", ep)

    # Платная половина — ВТОРЫМ проходом, после текстовой работы всех серий.
    # Тот же принцип, что и с отложенными сериями (D-7): бесплатная работа по
    # сезону не должна ждать, пока досняли предыдущую серию. Внутри прохода
    # порядок обычный — по сериям.
    for ep in episode_ids(project_dir):
        if not (project_dir / "episodes" / ep / "shots.json").exists():
            continue
        paid = _paid_stage(project_dir, ep)
        if paid is not None:
            return (paid, ep)
    return deferred[0] if deferred else None


# Платная половина: что делать, когда план съёмки написан. Порядок следует из
# зависимостей — отрезки строятся на принятых кадрах, звук от них не зависит,
# фоли нужен готовый отрезок, липсинку нужен ещё и голос, монтаж — последним.
def _pending(manifest, item_id: str) -> bool:
    """Единица, которую ещё предстоит сгенерировать.

    `generated` считается сделанным: он ждёт ЧЕЛОВЕКА, а не машину, и гнать
    генерацию повторно нельзя — за неё уже заплачено.
    """
    try:
        return manifest.get(item_id)["status"] not in (
            "done", "accepted_with_notes", "generated")
    except ManifestError:
        return True


def _shots_usable(project_dir: Path, episode: str) -> bool:
    """Читается ли план съёмки серии.

    Один ответ на этот вопрос для обеих половин резолвера: бесплатная не должна
    идти писать звук к непригодному плану, платная — тратить по нему деньги.
    Пустой `{}` тоже непригоден: раньше резолвер смотрел на существование файла
    и считал такую раскадровку сделанной.
    """
    from factory.shots import ShotsError, load_shots

    try:
        load_shots(Path(project_dir) / "episodes" / episode / "shots.json",
                   project_dir, episode)
    except (ShotsError, OSError, ValueError):
        return False
    return True


def _paid_stage(project_dir: Path, episode: str) -> str | None:
    """Первый незакрытый платный шаг эпизода или None, если всё сделано."""
    from factory.audio_plan import AudioPlanError, load_audio_plan
    from factory.shots import ShotsError, load_shots

    episode_dir = Path(project_dir) / "episodes" / episode
    try:
        shots = load_shots(episode_dir / "shots.json", project_dir, episode)
    except (ShotsError, OSError, ValueError):
        # Непригодный план съёмки — работа этапа storyboard, не платной половины.
        return "storyboard"

    manifest_path = Path(project_dir) / "manifest.json"
    # Manifest сам переживает отсутствие файла (пустая память проекта), поэтому
    # ветвление по exists() тут было тождественным.
    manifest = Manifest(manifest_path)

    if any(_pending(manifest, f"{episode}/storyboard/{f['n']:03d}")
           for f in shots.get("frames", [])):
        # Отдельное имя, чтобы не путать с текстовым этапом storyboard: там
        # пишется shots.json, здесь тратятся деньги на кадры.
        return "storyboard_generate"

    accepted = {"done", "accepted_with_notes"}

    def all_accepted(prefix: str, numbers) -> bool:
        """Все ли единицы приняты ревью. `generated` — НЕ принято.

        Проверка нужна перед каждой стадией, которая строится на чужом
        результате: `_pending` считает `generated` сделанным (машине там делать
        нечего), но следующая стадия требует именно ПРИНЯТОГО и отказывает
        кодом 3. Без этой проверки резолвер называл стадию, которую её
        собственный гейт на том же состоянии отбивает (ревью 2026-09-05).
        """
        for n in numbers:
            try:
                status = manifest.get(f"{episode}/{prefix}/{n:03d}")["status"]
                if status not in accepted:
                    return False
            except ManifestError:
                return False
        return True

    frame_numbers = [f["n"] for f in shots.get("frames", [])]
    if not all_accepted("storyboard", frame_numbers):
        return None  # кадры сгенерированы и ждут человека — машине делать нечего

    segment_numbers = [s["n"] for s in shots.get("segments", [])]
    if any(_pending(manifest, f"{episode}/segments/{n:03d}")
           for n in segment_numbers):
        return "segments"
    # Симметрично кадрам: звук, фоли, липсинк и монтаж строятся на ПРИНЯТЫХ
    # отрезках, поэтому дальше идти нельзя, пока их не приняли.
    if not all_accepted("segments", segment_numbers):
        return None

    audio_file = episode_dir / "audio.json"
    if audio_file.exists():
        try:
            plan = load_audio_plan(audio_file, shots)
        except (AudioPlanError, OSError, ValueError):
            return "audio"
        if any(_pending(manifest, f"{episode}/audio/{e['id']}")
               for name in ("voice_lines", "music_cues", "sfx")
               for e in plan.get(name, [])):
            return "audio"
        if any(_pending(manifest, f"{episode}/foley/{e['id']}")
               for e in plan.get("foley", [])):
            return "foley"
        if any(_pending(manifest, f"{episode}/lipsync/{e['segment']:03d}")
               for e in plan.get("voice_lines", []) if e.get("lipsync")):
            return "lipsync"

    # Готовый файл эпизода — единственный признак, что монтаж уже сделан.
    # Форматов может быть несколько (16x9 и 9x16), хватает любого.
    final = episode_dir / "final"
    rendered = final.exists() and any(final.glob("*.mp4"))
    return None if rendered else "render"


# --- обратная связь (переехало из scripts/factory.py 2026-09-05) ---
# Логика доменная, а не CLI: то же состояние нужно панели управления, и
# держать его в скрипте значило бы импортировать скрипт из библиотеки.
def _edited_since_commit(path: Path) -> bool:
    """Правил ли человек ТЕЛО файла после того, как его закоммитил скилл этапа.

    Скилл коммитит артефакт сразу после генерации (спека §11), поэтому git и есть
    база сравнения «что написала машина» против «что стало после человека». Но
    сравнивать нужно тело, а не файл целиком: `cmd_approve` тоже переписывает
    frontmatter (status/approved_at/хеши зависимостей) и не коммитит — сравнение
    всего файла считало бы это правкой человека, хотя человек файл не открывал
    (находка D-1 первого живого прогона). Frontmatter служебный, его пишет машина;
    правка человека — это изменение значимого тела.
    """
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                          capture_output=True, encoding="utf-8", errors="replace")
    # Вне git-репозитория (и при любой другой невозможности определить корень)
    # git отдаёт ненулевой код вместе с ошибкой в stderr — считаем «не правлен»,
    # как и раньше.
    if root.returncode != 0 or root.stderr.strip():
        return False
    rel = Path(os.path.relpath(path, root.stdout.strip())).as_posix()
    result = subprocess.run(["git", "show", f"HEAD:{rel}"],
                            capture_output=True, encoding="utf-8", errors="replace")
    # Файла нет в HEAD (новый, ещё не коммитился) — тот же принцип: непустой
    # stderr значит git не смог отдать версию, сравнивать не с чем.
    if result.returncode != 0 or result.stderr.strip():
        return False
    try:
        _, head_body = split_frontmatter(result.stdout, path)
    except ArtifactError:
        # Версия из HEAD не разбирается (битый frontmatter в самом коммите) — не
        # наша забота здесь; падать на этом нельзя, как и на отсутствующем файле.
        return False
    try:
        current_body = load_artifact(path).body
    except (ArtifactError, OSError):
        # Симметрично: если рабочая копия сама не разбирается, сравнивать не с
        # чем — это забота artifact_state/cmd_status, не эта функция.
        return False
    return body_sha(current_body) != body_sha(head_body)


def effective_feedback(path: Path) -> str:
    """Состояние обратной связи с поправкой на факт правки.

    Поле в артефакте само по себе не знает, что человек его правил: в `pending` его
    никто не переводит. Без этой поправки `/factory-feedback` не находил бы ни одной
    строки и вся петля §11 была бы мёртвой (находка финального ревью).
    """
    state = feedback_state(path)
    if state == "none" and _edited_since_commit(path):
        return "pending"
    return state


# --- перечень текстовых артефактов (переехало из scripts/factory.py 2026-09-05) ---
# Список общий для CLI и панели управления. Панель сначала собирала его
# своим глобом bible/*.md и показывала craft-notes.md как broken: это не
# frontmatter-артефакт, у него нет ни kind, ни status. Вторая копия списка
# разошлась с первой в тот же день, когда появилась.
# Персонажи не скаффолдятся: их состав известен только после сценария.
SCAFFOLD = {
    "bible/idea.md": "idea",
    "bible/season-arc.md": "season-arc",
    "bible/style-guide.md": "style-guide",
}


def scaffold_project(project_dir: Path) -> list[str]:
    """Создать пустые артефакты и каталоги серий; вернуть то, что создано.

    Одно тело для `factory.py init` и для мастера создания проекта в панели:
    два скаффолдера однажды разошлись бы в списке файлов, и половина проекта
    зависела бы от того, откуда его завели. Печать остаётся у CLI — здесь
    только действие.

    Идемпотентно: написанное не затирается. Повторный вызов на живом проекте
    ничего не теряет.
    """
    from factory.artifact import save_artifact

    project_dir = Path(project_dir)
    created: list[str] = []
    for rel, kind in SCAFFOLD.items():
        path = project_dir / rel
        if path.exists():
            continue
        save_artifact(Artifact(path=path, meta={"kind": kind, "status": "draft"},
                               body=""))
        created.append(rel)
    for ep in episode_ids(project_dir):
        (project_dir / "episodes" / ep).mkdir(parents=True, exist_ok=True)
    return created


def project_artifacts(project_dir: Path) -> list[Path]:
    paths = [project_dir / rel for rel in SCAFFOLD]
    paths += sorted((project_dir / "bible" / "characters").glob("*.md"))
    paths += sorted((project_dir / "episodes").glob("*/script.md"))
    research = project_dir / "research.md"
    if research.exists():
        paths.append(research)
    return paths
