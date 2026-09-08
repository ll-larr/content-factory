"""Логика панели управления: состояние проектов и действия человека.

HTTP здесь нет — сервер (`scripts/serve.py`) остаётся тонкой обёрткой. Так
проверяемо: состояние и действия тестируются без сокетов, а в сервере не
остаётся ничего, что стоило бы тестировать отдельно.

Панель НЕ дублирует логику конвейера: состояние она берёт у `preprod`, `Manifest`
и `montage`, действия делает через `Manifest`. Копия любой из этих проверок дала
бы четвёртый ответ на вопрос, на который уже отвечают три команды (D-3 первого
живого прогона).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from factory import estimate, keys
from factory.manifest import Manifest, ManifestError
from factory.preprod import (STAGE_LABELS, artifact_state, effective_feedback,
                             episode_ids, next_stage, project_artifacts)
from factory.project import (FORMAT_LABELS, LANGUAGES, ProjectError,
                             load_project)
from factory.providers import get_provider
from factory.text import engine as text_engine
from factory.safety import inside, is_safe_name
from factory.tasks import TaskBusyError

# Статусы, в которых единица ждёт ЧЕЛОВЕКА, а не машину. Панель существует ради
# них: всё остальное человеку смотреть незачем.
AWAITING_REVIEW = "generated"


class WebappError(ValueError):
    """Отказ по контракту запроса. Сервер превращает его в 400, не в 500."""


def list_projects(projects_root: Path) -> list[str]:
    """Каталоги, в которых лежит бриф. Папка без project.json — не проект."""
    root = Path(projects_root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir()
                  if (p / "project.json").exists())


def _artifacts(project_dir: Path) -> list[dict]:
    """Текстовые артефакты с состоянием одобрения — тот же список, что у CLI."""
    return [{"path": path.relative_to(project_dir).as_posix(),
             "state": artifact_state(project_dir, path),
             "feedback": effective_feedback(path)}
            for path in project_artifacts(project_dir)]


def project_overview(project_dir: Path,
                     knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Всё, что панель показывает по проекту, одним словарём."""
    project_dir = Path(project_dir)
    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        raise WebappError(f"непригодный project.json: {e}") from None

    manifest_path = project_dir / "manifest.json"
    manifest = Manifest(manifest_path)
    items = manifest.data.get("items", {})

    episodes = []
    for ep in episode_ids(project_dir):
        ep_items = [
            {"id": item_id,
             "kind": item.get("kind"),
             "status": item.get("status"),
             "file": _relative_file(project_dir, item.get("file")),
             "reject_reason": item.get("reject_reason"),
             "attempts": item.get("attempts", 0)}
            for item_id, item in sorted(items.items())
            if item_id.startswith(f"{ep}/")
        ]
        final = project_dir / "episodes" / ep / "final"
        episodes.append({
            "id": ep,
            "items": ep_items,
            # Проверка фактов — состояние СЕРИИ, а не проекта, поэтому лежит
            # здесь. У жанра, который её не требует, ключа нет вовсе: пустой
            # блок на экране мультфильма означал бы работу, которой не будет.
            "fact_check": _fact_check_block(project_dir, ep, knowledge_dir),
            "awaiting": sum(1 for i in ep_items
                            if i["status"] == AWAITING_REVIEW),
            "final": sorted(
                f.relative_to(project_dir).as_posix()
                for f in (final.glob("*.mp4") if final.exists() else [])),
        })

    stage = next_stage(project_dir)
    budget = project.raw.get("budget_usd")
    return {
        "name": project.name,
        "type": project.type,
        "genre": genre_summary(project, knowledge_dir),
        "format": project.format,
        "format_label": FORMAT_LABELS.get(project.format, project.format),
        "aspect": project.aspect,
        "theme": project.theme,
        "language": project.language,
        "languages": [{"code": code, "label": label}
                      for code, label in LANGUAGES.items()],
        # Режим: явный из брифа, иначе дефолт жанра. Считаем по карточке,
        # которая уже прочитана здесь, — у Project её может не быть, если он
        # загружен не из корня репозитория.
        "visual_mode": project.raw.get(
            "visual_mode", genre_summary(project, knowledge_dir)["default_visual_mode"]),
        "visual_modes": genre_summary(project, knowledge_dir)["visual_modes"],
        "segment_seconds": project.segment_seconds,
        "models": project.models,
        "artifacts": _artifacts(project_dir),
        "episodes": episodes,
        # Референсы персонажей живут вне эпизодов — показываем отдельно, иначе
        # человек не увидит того, что ждёт его приёмки прямо сейчас.
        "character_refs": [
            {"id": item_id, "status": item.get("status"),
             "file": _relative_file(project_dir, item.get("file"))}
            for item_id, item in sorted(items.items())
            if item_id.startswith("bible/characters/")
        ],
        "next": ({"stage": stage[0], "episode": stage[1],
                  "label": STAGE_LABELS.get(stage[0], stage[0])}
                 if stage else None),
        "budget": {"limit": float(budget) if budget is not None else None,
                   "spent": manifest.credits_total()},
    }


def _fact_check_block(project_dir: Path, episode: str,
                      knowledge_dir: Path | str = "knowledge") -> dict | None:
    """Что показать про проверку фактов этой серии; None — жанр её не требует.

    Вердикт и его формулировка берутся у `factcheck.report_state`, который
    поверх `report_problem` — того же, чем отказывает `factory.py approve`.
    Панель не считает состояние заново: разойдись она с гейтом, человек читал бы
    на экране одно, а в отказе одобрения другое.
    """
    from factory.text.factcheck import genre_requires_check, report_state

    if not genre_requires_check(project_dir, knowledge_dir):
        return None
    return report_state(project_dir, episode)


def _relative_file(project_dir: Path, file: str | None) -> str | None:
    """Путь файла относительно проекта — ровно то, что панель отдаёт по HTTP.

    Манифест хранит путь так, как его видел генератор: он запускается из КОРНЯ
    репозитория, поэтому там лежит `projects/<проект>/...`, а не `bible/...`.
    Считать такой путь относительным к каталогу проекта значит получить
    `projects/<проект>/projects/<проект>/...` — панель показывала битые картинки
    именно поэтому. Пробуем оба прочтения и берём то, что существует.

    Файл снаружи проекта не отдаём вовсе: манифест — обычный JSON, и отдавать
    по сети что попало из-за записи в нём нельзя.
    """
    if not file:
        return None
    raw = Path(file)
    candidates = [raw] if raw.is_absolute() else [Path.cwd() / raw, project_dir / raw]
    for candidate in candidates:
        if candidate.exists() and inside(project_dir, candidate):
            return candidate.resolve().relative_to(
                Path(project_dir).resolve()).as_posix()
    return None


def media_path(project_dir: Path, rel: str) -> Path:
    """Абсолютный путь файла проекта для отдачи по HTTP.

    Containment обязателен: `rel` приходит из URL, то есть от кого угодно, кто
    достучался до порта. Проверка та же, что у монтажного листа и у ссылок
    кадров, — из `factory.safety`, а не своя копия.
    """
    project_dir = Path(project_dir)
    candidate = project_dir / rel
    if Path(rel).is_absolute() or not inside(project_dir, candidate):
        raise WebappError(f"путь вне проекта: {rel}")
    if not candidate.is_file():
        raise WebappError(f"нет файла: {rel}")
    return candidate.resolve()


# Действия ревью и их переходы. Панель не изобретает своих: те же, что у
# scripts/review.py, потому что состояние одно.
REVIEW_ACTIONS = {"accept": "done", "accept-notes": "accepted_with_notes",
                  "reject": "rejected", "requeue": "pending"}


def review_action(project_dir: Path, item_id: str, action: str,
                  reason: str | None) -> dict:
    """Провести единицу манифеста через приёмку. Возвращает новое состояние."""
    if action not in REVIEW_ACTIONS:
        raise WebappError(
            f"неизвестное действие {action!r}; известны {sorted(REVIEW_ACTIONS)}")
    # Отклонение без причины бесполезно: причина уходит в манифест и потом
    # объясняет, почему кадр переснимали. Пустая строка — та же беспричинность.
    if action == "reject" and not (reason or "").strip():
        raise WebappError("отклонение требует причину")
    manifest = Manifest(Path(project_dir) / "manifest.json")
    fields = {}
    if action == "reject":
        fields["reject_reason"] = reason.strip()
    elif action == "accept-notes" and reason:
        fields["notes"] = reason.strip()
    try:
        manifest.set_status(item_id, REVIEW_ACTIONS[action], **fields)
    except ManifestError as e:
        raise WebappError(str(e)) from None
    manifest.save()
    return manifest.get(item_id)


def approve_artifact(project_dir: Path, rel: str) -> dict:
    """Одобрить текстовый артефакт — тем же кодом, что и CLI.

    Скилл и панель обязаны ставить одно и то же состояние, поэтому здесь вызов
    `factory.py approve`, а не своя запись во frontmatter (правило спеки:
    `status: approved` ставит ТОЛЬКО approve).
    """
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "factory.py"
    out = subprocess.run(
        [sys.executable, str(script), "approve", "--project", str(project_dir), rel],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise WebappError((out.stdout + out.stderr).strip() or "approve не удался")
    return {"path": rel, "state": artifact_state(project_dir, project_dir / rel)}


# --- запуск стадий из панели ----------------------------------------------

# Стадии, которые панель имеет право запустить. Список закрытый: имя приходит из
# браузера и становится аргументом командной строки, а «что угодно» в аргументах
# команды — это не свобода, а дыра.
PAID_RUNNABLE = ("storyboard", "segments", "audio", "foley", "lipsync")
RUNNABLE_STAGES = PAID_RUNNABLE + ("render",)

# Текстовые стадии: бесплатны для провайдеров видео, но платны по токенам, если
# движок — модель по ключу. Список закрытый по той же причине, что у платных:
# имя приходит из браузера и становится аргументом команды.
TEXT_RUNNABLE = ("pitch", "research", "story", "script", "characters",
                 "storyboard", "audio", "factcheck")


def run_stage(runner, projects_root: Path, project: str, episode: str,
              stage: str) -> dict:
    """Запустить стадию тем же CLI, каким её запускает человек в терминале.

    Смету панель показывает ДО этого вызова, поэтому платные стадии идут с
    `--yes`: второй вопрос задавался бы в терминале, которого никто не видит.
    """
    if stage not in RUNNABLE_STAGES:
        raise WebappError(
            f"неизвестная стадия {stage!r}; известны: {', '.join(RUNNABLE_STAGES)}")
    if not is_safe_name(project) or not is_safe_name(episode):
        raise WebappError("недопустимое имя проекта или серии")

    project_dir = Path(projects_root) / project
    if not (project_dir / "project.json").is_file():
        raise WebappError(f"нет {project_dir / 'project.json'}")

    scripts_dir = Path(__file__).resolve().parent.parent
    if stage == "render":
        cmd = [sys.executable, str(scripts_dir / "render.py"),
               "--project", str(project_dir), "--episode", episode]
        kind = "render"
    else:
        cmd = [sys.executable, str(scripts_dir / "generate_batch.py"),
               "--project", str(project_dir), "--episode", episode,
               "--stage", stage, "--yes"]
        kind = "stage"

    try:
        return runner.start(cmd, {"kind": kind, "project": project,
                                  "episode": episode, "stage": stage})
    except TaskBusyError as e:
        raise WebappError(str(e)) from None


def episode_estimate(project_dir: Path, episode: str,
                     knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Смета остатка эпизода — та же, что печатает `factory.py estimate`."""
    try:
        return estimate.episode_estimate(project_dir, episode, knowledge_dir)
    except estimate.EstimateError as e:
        raise WebappError(str(e)) from None


def keys_state(root: Path | str = Path(".")) -> list[dict]:
    """Состояние ключей: маски и роли, без значений."""
    return keys.read_state(root)


def set_key(root: Path | str, provider: str, value: str) -> dict:
    """Записать ключ провайдера. Отказ — по контракту запроса, не 500."""
    try:
        return keys.write_key(root, provider, value)
    except KeyError as e:
        raise WebappError(f"неизвестный провайдер: {provider}") from None
    except ValueError as e:
        raise WebappError(str(e)) from None
    except OSError as e:
        raise WebappError(f"не удалось записать .env: {e}") from None


def balances(knowledge_dir: Path | str = Path("knowledge")) -> list[dict]:
    """Балансы провайдеров — там, где провайдер умеет их отдавать.

    Ни одна строка не притворяется нулём: `null` значит «спросить нечем» или
    «ключа нет», и причина написана рядом. По балансу человек решает, хватит ли
    денег на съёмку, и выдуманное число здесь хуже отсутствующего.
    """
    from factory.providers import is_search_provider

    rows = []
    for provider_name, spec in keys.PROVIDERS.items():
        row = {"provider": provider_name, "balance": None, "reason": ""}
        # Поисковый провайдер не генерирует медиа и своего счёта в долларах не
        # показывает: у Tavily кредиты, а не деньги. Показывать человеку
        # трейсбек «unknown provider» вместо этого — врать о причине прочерка.
        if is_search_provider(provider_name):
            row["reason"] = ("поиск для проверки фактов; счёт в кредитах, "
                             "баланс через API не отдаётся")
            rows.append(row)
            continue
        try:
            provider = get_provider(provider_name.lower(), knowledge_dir)
        except Exception as e:                       # noqa: BLE001 - см. reason
            row["reason"] = str(e)
            rows.append(row)
            continue

        if not provider.supports_balance:
            row["reason"] = "провайдер не отдаёт баланс через API"
        elif not os.environ.get(spec["env"]):
            row["reason"] = "ключ не задан"
        else:
            try:
                row["balance"] = provider.balance()
            except Exception as e:                   # noqa: BLE001 - см. reason
                row["reason"] = str(e)
        rows.append(row)
    return rows


# --- жанр, язык и режим в панели ------------------------------------------

def genre_summary(project, knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Карточка жанра в том виде, в каком её показывает панель.

    Панель перестраивается по жанру: у познавательного нет персонажей, значит нет
    ни стадии, ни кнопки, ни строки в лестнице. Один источник правды — карточка.
    """
    from factory.genres import KNOWN_STAGES, GenreError, load_genre

    try:
        card = load_genre(knowledge_dir, project.genre)
    except GenreError as e:
        # Карточка недоступна — панель всё равно должна открыться и показать
        # проект: иначе одна ненайденная карточка прячет и очередь приёмки, и
        # бюджет. Проблему показываем строкой, а не отказом на весь обзор.
        return {"id": project.genre, "label": project.genre,
                "stages": list(KNOWN_STAGES), "lipsync": True,
                "has_characters": True, "narrator": False, "fact_check": "none",
                "captions": "shorts_only", "visual_modes": [project.visual_mode],
                "default_visual_mode": project.visual_mode, "problem": str(e)}

    return {"id": card["id"], "label": card["label"], "stages": card["stages"],
            "lipsync": card["lipsync"], "has_characters": card["has_characters"],
            "narrator": card["narrator"], "fact_check": card["fact_check"],
            "captions": card["captions"], "visual_modes": card["visual_modes"],
            "default_visual_mode": card["default_visual_mode"]}


def set_project_settings(project_dir: Path, changes: dict,
                         knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Записать в бриф язык и режим кадров.

    Правится ТОЧЕЧНО, поверх прочитанного файла: в project.json лежат тема,
    бюджет и модели, и переписать его целиком значило бы потерять всё, чего
    панель не знает.
    """
    from factory.project import LANGUAGES

    path = Path(project_dir) / "project.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise WebappError(f"непригодный project.json: {e}") from None

    if "language" in changes:
        code = changes["language"]
        if code not in LANGUAGES:
            raise WebappError(
                f"неизвестный язык {code!r}; известны: {sorted(LANGUAGES)}")
        data["language"] = code

    if "visual_mode" in changes:
        mode = changes["visual_mode"]
        genre = data.get("genre") or load_project(path).genre
        from factory.genres import GenreError, load_genre
        try:
            card = load_genre(knowledge_dir, genre)
        except GenreError as e:
            raise WebappError(str(e)) from None
        if mode not in card["visual_modes"]:
            raise WebappError(
                f"режим {mode!r} не разрешён жанром {card['label']!r} "
                f"(разрешены: {card['visual_modes']})")
        data["visual_mode"] = mode

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"language": data.get("language"), "visual_mode": data.get("visual_mode")}


# --- создание проекта ------------------------------------------------------

# Модели нового проекта. Оба выбора — самые дешёвые из ПОДТВЕРЖДЁННЫХ живой
# генерацией, и оба на одном провайдере: заводя первый проект, человек ставит
# один ключ, а не два. Менять модели человек будет в панели (задача C бэклога);
# до тех пор это правка project.json, и молчаливый дефолт обязан быть дешёвым и
# рабочим, а не «каким-нибудь».
DEFAULT_MODELS = {
    "image": {"model": "flux_2_klein", "provider": "runware"},
    "video": {"model": "vidu_q2_turbo", "provider": "runware"},
}

# Что мастер спрашивает и в каких границах. Числа — не вкус, а защита от опечатки
# в поле ввода: сезон из тысячи серий и ролик на сутки заказывают не мышкой.
MAX_EPISODES = 200
MAX_DURATION_SEC = 3 * 60 * 60


def new_project_options(knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Из чего человек выбирает в мастере: жанры, форматы, языки.

    Список жанров берётся из карточек, а не из литерала в панели: карточка —
    единственное место, где записано, какие жанры существуют.
    """
    from factory.genres import GenreError, all_genres

    try:
        cards = all_genres(knowledge_dir)
    except GenreError as e:
        raise WebappError(str(e)) from None

    return {
        "genres": [{"id": c["id"], "label": c["label"],
                    # `animated` панель спрашивает не из любопытства: от него
                    # зависит выведенный `type`, а от типа — обязательность
                    # аудитории в брифе. Поле приходит с сервера, чтобы правило
                    # не пришлось повторять в браузере второй раз.
                    "animated": bool(c["animated"]),
                    "has_characters": bool(c["has_characters"]),
                    "fact_check": c["fact_check"],
                    "visual_modes": list(c["visual_modes"]),
                    "default_visual_mode": c["default_visual_mode"]}
                   for c in cards],
        "formats": [{"id": fid, "label": label}
                    for fid, label in FORMAT_LABELS.items()],
        "languages": [{"id": code, "label": label}
                      for code, label in LANGUAGES.items()],
        "models": DEFAULT_MODELS,
    }


def _positive_int(value, field: str, limit: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise WebappError(f"{field}: нужно целое число, получено {value!r}") from None
    if number < 1 or number > limit:
        raise WebappError(f"{field}: допустимо от 1 до {limit}, получено {number}")
    return number


def create_project(projects_root: Path | str, data: dict,
                   knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Создать дерево проекта: project.json, manifest.json, bible/, episodes/.

    Скаффолд артефактов делает `preprod.scaffold_project` — тот же, которым
    работает `factory.py init`: два скаффолдера однажды разошлись бы, и половина
    проекта зависела бы от того, откуда его завели.

    `type` не спрашивается у человека: он выводится из жанра и формата
    (`project.type_for`). Легаси-поле, набранное руками, однажды разойдётся с
    жанром, и никто этого не заметит.
    """
    from factory.genres import GenreError, load_genre
    from factory.preprod import scaffold_project
    from factory.project import FORMAT_ASPECT, normalize_format, type_for

    name = str(data.get("name") or "").strip()
    if not name:
        raise WebappError("имя проекта пустое")
    # Имя становится именем каталога: та же проверка, что у всех данных,
    # приходящих из браузера и превращающихся в путь (safety.is_safe_name).
    if not is_safe_name(name):
        raise WebappError(
            f"имя {name!r} не годится как имя папки: без слэшей, точек в начале "
            "и служебных символов")

    theme = str(data.get("theme") or "").strip()
    if not theme:
        raise WebappError("тема проекта пустая: по ней работает вся первая половина")

    genre_id = str(data.get("genre") or "").strip()
    try:
        card = load_genre(knowledge_dir, genre_id)
    except GenreError as e:
        raise WebappError(str(e)) from None

    # Старое имя формата принимается и разворачивается в текущее: бриф, набитый
    # по прошлой документации, не должен отбиваться на ровном месте.
    fmt = normalize_format(str(data.get("format") or "").strip())
    if fmt not in FORMAT_ASPECT:
        raise WebappError(
            f"неизвестный формат {fmt!r}; известны: {sorted(FORMAT_ASPECT)}")

    language = str(data.get("language") or "ru")
    if language not in LANGUAGES:
        raise WebappError(
            f"неизвестный язык {language!r}; известны: {sorted(LANGUAGES)}")

    root = Path(projects_root)
    project_dir = root / name
    if not inside(root, project_dir):
        raise WebappError(f"путь проекта выходит за пределы {root}")
    if project_dir.exists():
        raise WebappError(
            f"проект {name!r} уже существует — выбери другое имя или открой его")

    ptype = type_for(card, fmt)
    brief: dict = {
        "name": name, "type": ptype, "genre": genre_id, "format": fmt,
        "theme": theme, "language": language,
        "models": {k: dict(v) for k, v in DEFAULT_MODELS.items()},
    }

    # Обязательные поля брифа зависят от типа, и спрашивать их надо здесь, а не
    # ловить отказом load_project после того, как каталог уже создан.
    if ptype in ("series", "animated_series"):
        brief["episodes"] = _positive_int(
            data.get("episodes"), "серий", MAX_EPISODES)
        brief["episode_duration_sec"] = _positive_int(
            data.get("episode_duration_sec"), "длительность серии",
            MAX_DURATION_SEC)
    else:
        brief["duration_sec"] = _positive_int(
            data.get("duration_sec"), "длительность", MAX_DURATION_SEC)

    if ptype in ("animated_film", "animated_series"):
        audience = str(data.get("audience") or "").strip()
        if not audience:
            raise WebappError(
                "рисованному жанру нужна аудитория (например «6-9» или «12+»): "
                "от неё зависит и текст, и картинка")
        brief["audience"] = audience

    visual_mode = str(data.get("visual_mode") or "").strip()
    if visual_mode and visual_mode not in card["visual_modes"]:
        raise WebappError(
            f"режим {visual_mode!r} не разрешён жанром {genre_id!r} "
            f"(разрешены: {card['visual_modes']})")
    if visual_mode:
        brief["visual_mode"] = visual_mode

    # `is_safe_name` отвечает только за то, что имя — один компонент пути и не
    # выводит наружу. Годность его для ФАЙЛОВОЙ СИСТЕМЫ решает она сама: на
    # Windows двоеточие, звёздочка и имена вроде `con` запрещены, и перечислять
    # их здесь значило бы держать свою копию правил чужой ОС. Дешевле и честнее
    # попробовать создать и передать отказ человеку словами.
    try:
        project_dir.mkdir(parents=True)
        (project_dir / "bible").mkdir()
        (project_dir / "episodes").mkdir()
    except OSError as e:
        raise WebappError(
            f"каталог проекта не создать: {e}. Скорее всего имя {name!r} "
            "не годится для файловой системы") from None
    (project_dir / "project.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Манифест — память завода. Пустой заводится сразу: иначе первая же платная
    # стадия создавала бы его молча, и «проект есть, памяти нет» было бы
    # состоянием, в котором панель ничего не показывает.
    (project_dir / "manifest.json").write_text(
        json.dumps({"items": {}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    # Бриф должен разбираться СРАЗУ: непригодный project.json, созданный самой
    # панелью, — это ошибка панели, и обнаружиться она обязана здесь, а не на
    # первом гейте. Недоделанный каталог при этом убирается: иначе имя занято
    # проектом, который не открывается, и повторить создание нечем.
    try:
        load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise WebappError(f"панель собрала непригодный бриф: {e}") from None

    created = scaffold_project(project_dir)
    return {"project": name, "type": ptype, "genre": genre_id, "format": fmt,
            "created": ["project.json", "manifest.json"] + created}


# --- модели по ролям -------------------------------------------------------

# Роли конвейера и то, чем каждая закрывается. Ключ — путь в `models` брифа,
# значение — какие карточки годятся и как роль называется человеку.
#
# Список закрытый и живёт здесь один раз: имя роли приходит из браузера и
# становится ключом в project.json. «Что угодно» в ключах брифа — не свобода,
# а способ получить проект, который не читается.
MODEL_ROLES: dict[str, dict] = {
    "image": {"label": "Кадры", "type": "image", "kind": None,
              "note": "по кадру на каждый план раскадровки"},
    "video": {"label": "Отрезки", "type": "video", "kind": None,
              "note": "оживляет кадр; в режиме «кадры» не используется"},
    "audio.tts": {"label": "Озвучка", "type": "audio", "kind": "tts",
                  "note": "реплики персонажей и диктора"},
    "audio.music": {"label": "Музыка", "type": "audio", "kind": "music",
                    "note": "подложка эпизода"},
    "audio.sfx": {"label": "Эффекты", "type": "audio", "kind": "sfx",
                  "note": "точечные звуки по плану"},
    "audio.foley": {"label": "Фоли", "type": "audio", "kind": "foley",
                    "note": "фактура из готового отрезка"},
    "audio.lipsync": {"label": "Липсинк", "type": "audio", "kind": "lipsync",
                      "note": "губы под уже записанную реплику"},
}


def _role_current(project, role: str) -> dict:
    """Что выбрано сейчас: модель, провайдер, тир. Пусто — роль не объявлена.

    Роль без записи в брифе — обычное состояние, а не ошибка: проект без звука
    валиден, эпизод просто собирается молча.
    """
    try:
        if role.startswith("audio."):
            kind = role.split(".", 1)[1]
            return {"model": project.audio_model(kind),
                    "provider": project.audio_provider(kind),
                    "tier": project.audio_tier(kind)}
        return {"model": getattr(project, f"{role}_model"),
                "provider": getattr(project, f"{role}_provider"),
                "tier": getattr(project, f"{role}_tier")}
    except (ProjectError, KeyError, AttributeError):
        return {"model": None, "provider": None, "tier": None}


def _card_price(card: dict, provider: str, project) -> float | None:
    """Цена карточки под ЭТОТ проект: его разрешение и длительность отрезка.

    Считается тем же `estimate_media_cost`, что и смета: показать в выборе одно
    число, а в смете другое — значит выбрать модель по цене, которой нет.
    """
    from factory.models import ModelError, estimate_media_cost

    pv = (card.get("providers") or {}).get(provider) or {}
    tier = pv.get("default_tier")
    duration = project.segment_seconds if card.get("type") == "video" else 0
    try:
        return estimate_media_cost(card, provider, project.resolution,
                                   duration, tier)
    except (ModelError, KeyError, TypeError, ValueError):
        return None


def _role_problems(card: dict, spec: dict, provider: str, project) -> list[str]:
    """Что мешает взять эту карточку в эту роль. Пусто — можно.

    ЕДИНСТВЕННОЕ место, где этот вопрос решается: его зовёт и список выбора, и
    запись выбора в бриф. Две проверки разошлись бы ровно тем, что панель
    предлагает модель, а сохранение её отбивает (D-3 — та же болезнь).
    """
    from factory.models import (validate_audio_model, validate_image_model,
                                validate_video_model)

    if spec["type"] == "image":
        return validate_image_model(card, provider)
    if spec["type"] == "video":
        return validate_video_model(card, project.segment_seconds, provider)
    return validate_audio_model(card, provider, spec["kind"])


def model_roles(project_dir: Path,
                knowledge_dir: Path | str = Path("knowledge")) -> list[dict]:
    """Роли проекта с кандидатами: что стоит, что подтверждено, что нельзя.

    Карточка со `status: skeleton` ПОКАЗЫВАЕТСЯ, но не выбирается: спрятать её
    значило бы скрыть от человека, что модель существует и ждёт живой пробы, а
    разрешить — обойти гейт трат, который стоит именно на статусе.

    Роли, которых нет у жанра (липсинк там, где губ в кадре нет), не
    показываются вовсе — тем же ответом, что даёт лестница стадий.
    """
    from factory.genres import stage_allowed
    from factory.models import all_cards

    project_dir = Path(project_dir)
    try:
        project = load_project(project_dir / "project.json")
        card_of_genre = project.genre_card(knowledge_dir)
    except (ProjectError, OSError, ValueError) as e:
        raise WebappError(str(e)) from None

    cards = all_cards(Path(knowledge_dir))
    rows = []
    for role, spec in MODEL_ROLES.items():
        if role == "audio.lipsync" and not stage_allowed(card_of_genre, "lipsync"):
            continue

        candidates = []
        for card in cards:
            if card.get("type") != spec["type"]:
                continue
            if spec["kind"] and card.get("audio_kind") != spec["kind"]:
                continue
            status = str(card.get("status", "")).split("#")[0].strip()
            providers = sorted(card.get("providers") or {})
            if not providers:
                # У карточки, ждущей живой пробы, блоки `providers` закрыты
                # комментарием — правило CLAUDE.md; у исторических карточек их
                # нет вовсе. Пропустить такую значит скрыть, что модель
                # существует; поэтому она в списке одной строкой и с причиной.
                candidates.append({
                    "model": card["id"], "provider": None, "status": status,
                    "selectable": False, "price": None,
                    "native_audio": bool(card.get("native_audio")),
                    "reason": "в карточке не объявлен ни один провайдер — "
                              "брать нечего, пока не будет живой пробы",
                })
                continue
            for provider in providers:
                # Годность решает ТОТ ЖЕ валидатор, что и запись выбора, — и
                # статус карточки, и сетку длительностей этого проекта. Своей
                # проверки здесь нет: предложить в списке то, что запись потом
                # отобьёт, значит дать человеку выбрать несуществующее.
                problems = _role_problems(card, spec, provider, project)
                candidates.append({
                    "model": card["id"],
                    "provider": provider,
                    "status": status,
                    "selectable": not problems,
                    "price": _card_price(card, provider, project),
                    # У видеомодели со своим звуком отрезок приходит с готовой
                    # дорожкой. Панель это показывает, потому что от этого
                    # зависит, нужен ли фоли отдельной генерацией.
                    "native_audio": bool(card.get("native_audio")),
                    "reason": "; ".join(problems),
                })

        rows.append({
            "role": role, "label": spec["label"], "note": spec["note"],
            "current": _role_current(project, role),
            "candidates": sorted(candidates,
                                 key=lambda c: (c["model"], c["provider"])),
        })
    return rows


def set_project_models(project_dir: Path, changes: dict,
                       knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Записать выбор моделей в бриф. Гейты — те же, что у платных стадий.

    Проверяем ДО записи: карточка существует, объявлена у выбранного провайдера,
    не `skeleton`, а для видео — ещё и держит длительность отрезка этого проекта.
    Записать негодную модель значит отложить отказ до момента, когда человек уже
    нажал «снимать».
    """
    from factory.models import (ModelError, find_card, validate_audio_model,
                                validate_image_model, validate_video_model)

    project_dir = Path(project_dir)
    path = project_dir / "project.json"
    try:
        project = load_project(path)
    except (ProjectError, OSError, ValueError) as e:
        raise WebappError(str(e)) from None

    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.setdefault("models", {})

    for role, choice in changes.items():
        if role not in MODEL_ROLES:
            raise WebappError(
                f"неизвестная роль {role!r}; известны {sorted(MODEL_ROLES)}")
        if not isinstance(choice, dict):
            raise WebappError(f"{role}: ждали объект с полями model и provider")
        model = str(choice.get("model") or "").strip()
        provider = str(choice.get("provider") or "").strip()
        tier = choice.get("tier") or None
        if not model or not provider:
            raise WebappError(f"{role}: нужны и model, и provider")

        try:
            card = find_card(Path(knowledge_dir), model)
        except (ModelError, OSError) as e:
            raise WebappError(str(e)) from None

        problems = _role_problems(card, MODEL_ROLES[role], provider, project)
        if problems:
            raise WebappError(f"{role}: " + "; ".join(problems))

        entry: dict = {"model": model, "provider": provider}
        if tier:
            entry["tier"] = str(tier)
        if role.startswith("audio."):
            models.setdefault("audio", {})[role.split(".", 1)[1]] = entry
        else:
            models[role] = entry

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    try:
        load_project(tmp)
    except (ProjectError, OSError, ValueError) as e:
        tmp.unlink(missing_ok=True)
        raise WebappError(f"бриф после правки не читается: {e}") from None
    tmp.replace(path)
    return {"models": data["models"]}


# --- окружение -------------------------------------------------------------

def environment_state(repo_root: Path | str = Path(".")) -> list[dict]:
    """Чего не хватает на машине — для баннера в панели.

    Список и формулировки живут в `factory/environment.py`, здесь только
    доставка: панель обязана говорить то же, что скажет `render.py`, отказываясь
    собирать эпизод.
    """
    from factory import environment

    return environment.check(repo_root)


# --- микшер ----------------------------------------------------------------

def mixer(project_dir: Path) -> dict:
    """Что сейчас в микшере проекта: дорожки, герои, дакинг, мастеринг.

    Значения и их дефолты живут в `montage.mix_settings` — там же, откуда их
    берёт монтажный лист. Панель не держит своей копии: сведение, которое
    человек видит, и сведение, которое уезжает в рендер, обязаны быть одним.

    Герои берутся из сценариев серий: микшеру нужен состав, а состав объявлен
    во frontmatter сценария и больше нигде.
    """
    from factory import montage
    from factory.preprod import episode_cast

    project_dir = Path(project_dir)
    try:
        project = load_project(project_dir / "project.json")
        settings = montage.mix_settings(project)
    except (ProjectError, montage.MontageError, OSError, ValueError) as e:
        raise WebappError(str(e)) from None

    cast: list[str] = []
    for episode in episode_ids(project_dir):
        for name in episode_cast(project_dir, episode):
            if name not in cast:
                cast.append(name)

    return {
        "tracks": [{"id": track, "label": montage.TRACK_LABELS[track],
                    "volume": settings["volumes"][track],
                    "default": montage.DEFAULT_VOLUMES[track],
                    "muted": track in settings["muted"]}
                   for track in montage.TRACKS],
        "speakers": [{"name": name,
                      "gain": settings["speakers"].get(name, 1.0)}
                     for name in cast],
        "duck": settings["duck"],
        "target_lufs": settings["target_lufs"],
        "max_volume": montage.MAX_VOLUME,
    }


def set_mixer(project_dir: Path, changes: dict) -> dict:
    """Записать микшер в бриф. Проверяет ТОТ ЖЕ `mix_settings`, что и рендер.

    Своей валидации здесь нет: разойдись она с монтажной — панель приняла бы
    значение, на котором рендер откажет.
    """
    from factory import montage

    project_dir = Path(project_dir)
    path = project_dir / "project.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise WebappError(f"project.json не читается: {e}") from None

    block = dict(data.get("mix") or {})
    if "volumes" in changes:
        volumes = dict(block.get("volumes") or {})
        volumes.update(changes["volumes"] or {})
        block["volumes"] = volumes
    if "muted" in changes:
        block["muted"] = changes["muted"] or []
    if "speakers" in changes:
        speakers = dict(block.get("speakers") or {})
        speakers.update(changes["speakers"] or {})
        block["speakers"] = speakers
    if "duck" in changes:
        duck = dict(block.get("duck") or {})
        duck.update(changes["duck"] or {})
        block["duck"] = duck
    if "target_lufs" in changes:
        block["target_lufs"] = changes["target_lufs"]

    data["mix"] = block
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    try:
        montage.mix_settings(load_project(tmp))
    except (ProjectError, montage.MontageError, OSError, ValueError) as e:
        tmp.unlink(missing_ok=True)
        raise WebappError(str(e)) from None
    tmp.replace(path)
    return mixer(project_dir)


# --- кастинг голосов -------------------------------------------------------

# Модель речи, чьи голоса показывает панель. Пока она одна: у ElevenLabs и Qwen
# свои наборы, и общий список предлагал бы голос, которого у выбранной модели
# нет. Когда моделей станет две, имя придёт из project.json.
VOICE_MODEL = "gemini_2_5_pro_tts"


def voice_catalog(language: str = "ru",
                  knowledge_dir: Path | str = Path("knowledge")) -> dict:
    """Голоса всех моделей речи — деревом: модель, пол, голос.

    Моделей может стать несколько (у каждого провайдера свой набор), поэтому
    ответ — СПИСОК моделей, а не одна. Список берётся из карточек голосов:
    добавить провайдера значит положить рядом ещё одну карточку, а не править
    панель.

    Пол — из карточки голосов, а не из имени пресета: имена о тембре не говорят
    ничего. Голоса без описания (у `Algieba` его нет в исходной карте) не
    прячутся, а идут отдельной группой: выбрать вслепую нечего, но и делать вид,
    что пресета не существует, нельзя.

    Описания в ответ не кладутся: в списке человек ориентируется по маркерам, а
    решает всё равно прослушиванием.
    """
    from factory import voices

    if language not in voices.SAMPLE_TEXT:
        raise WebappError(
            f"неизвестный язык проб {language!r}; "
            f"известны {sorted(voices.SAMPLE_TEXT)}")

    models = []
    for model in voices.available_models(knowledge_dir):
        try:
            rows = voices.catalog(knowledge_dir, model, language)
        except voices.VoicesError as e:
            raise WebappError(str(e)) from None

        groups: dict[str, list[dict]] = {"female": [], "male": [], "unknown": []}
        for row in rows:
            groups[row["gender"]].append({
                "preset": row["preset"],
                "markers": row["markers"],
                "sample": row["sample"],
                "sample_url": (f"/voice-sample/{model}/{language}/"
                               f"{row['preset']}.mp3") if row["sample"] else None,
            })
        models.append({
            "id": model,
            "label": voices.model_label(knowledge_dir, model),
            "groups": [{"id": gid, "label": voices.GENDER_LABELS[gid],
                        "voices": groups[gid]}
                       for gid in ("female", "male", "unknown") if groups[gid]],
            "missing": sum(1 for row in rows if not row["sample"]),
            "total": len(rows),
        })

    return {
        "language": language,
        "phrase": voices.SAMPLE_TEXT[language],
        "models": models,
        "missing": sum(m["missing"] for m in models),
        "total": sum(m["total"] for m in models),
    }


def voice_sample_file(model: str, language: str, preset: str,
                      knowledge_dir: Path | str = Path("knowledge")) -> Path:
    """Файл пробы для отдачи по HTTP. Все три имени приходят из URL."""
    from factory import voices

    if not all(is_safe_name(part) for part in (model, language, preset)):
        raise WebappError("недопустимое имя модели, языка или пресета")
    path = voices.sample_path(knowledge_dir, model, language, preset)
    root = Path(knowledge_dir)
    if not inside(root, path):
        raise WebappError(f"путь вне {root}")
    if not path.is_file():
        raise WebappError(f"пробы {preset} на языке {language} ещё нет")
    return path.resolve()


def run_voice_samples(runner, language: str = "ru", model: str = VOICE_MODEL,
                      voices_wanted: list[str] | None = None) -> dict:
    """Снять недостающие пробы — тем же CLI, каким их снимает человек.

    Задача сервера, а не вкладки: тридцать генераций идут минутами, и закрытая
    вкладка не должна обрывать оплаченную работу. Логику гейта трат и сметы
    панель не дублирует — она внутри `voice_samples.py`.
    """
    from factory import voices as voices_mod

    if language not in voices_mod.SAMPLE_TEXT:
        raise WebappError(f"неизвестный язык проб {language!r}")
    # Имя модели приходит из браузера и становится аргументом команды: список
    # закрытый, и берётся он из карточек — там же, где панель взяла его для
    # показа. Второго списка моделей речи не заводить.
    known = voices_mod.available_models(Path("knowledge"))
    if model not in known:
        raise WebappError(
            f"неизвестная модель голосов {model!r}; известны {known}")

    scripts_dir = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, str(scripts_dir / "voice_samples.py"),
           "--model", model, "--language", language, "--yes"]
    for preset in voices_wanted or []:
        if not is_safe_name(preset):
            raise WebappError(f"недопустимое имя пресета {preset!r}")
        cmd += ["--voice", preset]

    try:
        return runner.start(cmd, {"kind": "voices", "project": None,
                                  "episode": None, "stage": "voice_samples"})
    except TaskBusyError as e:
        raise WebappError(str(e)) from None


# --- текстовые стадии ------------------------------------------------------

def text_stages(project_dir: Path,
                knowledge_dir: Path | str = Path("knowledge")) -> list[dict]:
    """Текстовые стадии, которые есть у жанра этого проекта.

    Панель не показывает кнопку того, чего в жанре не существует: у
    познавательного нет персонажей, и кнопка «Персонажи» была бы обещанием,
    которое гейт немедленно нарушит.
    """
    from factory.genres import GenreError, load_genre, stage_allowed
    from factory.text.stages import STAGES

    try:
        project = load_project(Path(project_dir) / "project.json")
        card = load_genre(knowledge_dir, project.genre)
    except (ProjectError, GenreError, OSError, ValueError) as e:
        raise WebappError(str(e)) from None

    rows = []
    for stage in STAGES.values():
        if stage.pipeline_stage and not stage_allowed(card, stage.pipeline_stage):
            continue
        # Проверка фактов существует ровно там, где жанр её объявил. Показать
        # её мультфильму значило бы предложить работу, которой нет; спрятать у
        # познавательного — пообещать одобрение, которое гейт не даст.
        if stage.requires_fact_check and card.get("fact_check") != "required":
            continue
        # Причина недоступности приходит вместе со стадией, а не считается в
        # браузере: ответ на «почему нельзя» в продукте один, и формулирует его
        # тот же код, что отбивает запуск.
        blocked = ""
        if stage.requires_fact_check:
            from factory.text.factcheck import availability
            ok, why = availability()
            blocked = "" if ok else why
        rows.append({"id": stage.id, "label": stage.label,
                     "interactive": stage.interactive,
                     "blocked": blocked,
                     "outputs": list(stage.outputs)})
    return rows


def text_engines() -> dict:
    """Чем можно писать тексты на этой машине и какие модели предложить."""
    from factory.text import catalog
    from factory.text.engine import engine_states
    from factory.text.factcheck import availability

    models: list[dict] = []
    problem = ""
    try:
        models = catalog.text_models()
    except catalog.CatalogError as e:
        problem = str(e)

    # Проверка фактов — не деталь движка, а условие существования жанра: без
    # неё познавательный сценарий не одобряется. Панель обязана сказать об этом
    # прямо, а не молча предложить кнопку, которая откажет.
    can_check, why_not = availability()
    return {"engines": engine_states(), "models": models, "problem": problem,
            "fact_check": {"available": can_check, "reason": why_not}}


def run_text_stage(project_dir: Path, stage_id: str, *, request: str = "",
                   episode: str | None = None, model: str | None = None,
                   engine: str | None = None,
                   repo_root: Path | str = Path(".")) -> dict:
    """Провести текстовую стадию: собрать промпт, спросить модель, записать файлы.

    Питч ничего не записывает: это разговор, и пока человек не выбрал вариант,
    записывать нечего. Остальные стадии пишут только в объявленные выходы.
    """
    from factory.text import factcheck as factcheck_mod
    from factory.text import stages as text_stages_mod
    from factory.text.engine import TextEngineError

    if stage_id == factcheck_mod.STAGE_ID:
        if not episode:
            raise WebappError("проверка фактов идёт по серии: выбери серию")
        try:
            chosen = text_engine.pick_engine(engine)
            result = factcheck_mod.run(project_dir, repo_root, episode,
                                       engine=chosen, model=model)
        except (TextEngineError, factcheck_mod.FactCheckError) as e:
            raise WebappError(str(e)) from None
        return {"stage": stage_id, "engine": chosen.name, "model": model,
                "answer": result["answer"], "written": result["written"],
                "verdict": result["verdict"]}

    try:
        prompt = text_stages_mod.build_prompt(
            stage_id, project_dir, repo_root, request=request, episode=episode)
    except text_stages_mod.StageError as e:
        raise WebappError(str(e)) from None

    try:
        chosen = text_engine.pick_engine(engine)
        answer = chosen.complete(prompt.system, prompt.user, model=model)
    except TextEngineError as e:
        raise WebappError(str(e)) from None

    written: list[str] = []
    if prompt.stage.outputs:
        try:
            files = text_stages_mod.parse_files(answer)
            written = text_stages_mod.write_files(
                stage_id, project_dir, files, episode=episode)
        except text_stages_mod.StageError as e:
            raise WebappError(str(e)) from None

    return {"stage": stage_id, "engine": chosen.name, "model": model,
            "answer": answer, "written": written}


def run_text_task(runner, projects_root: Path, project: str, stage_id: str, *,
                  request: str = "", episode: str | None = None,
                  model: str | None = None, engine: str | None = None,
                  repo_root: Path | str = Path(".")) -> dict:
    """Текстовая стадия как долгая задача сервера.

    Модель думает минутами — столько же, сколько снимается отрезок. Держать это
    во вкладке нельзя по той же причине: закрытая вкладка не должна обрывать уже
    начатую работу, за которую платят по токенам.
    """
    if stage_id not in TEXT_RUNNABLE:
        raise WebappError(
            f"неизвестная текстовая стадия {stage_id!r}; "
            f"известны: {sorted(TEXT_RUNNABLE)}")
    if not is_safe_name(project) or (episode and not is_safe_name(episode)):
        raise WebappError("недопустимое имя проекта или серии")

    project_dir = Path(projects_root) / project
    if not (project_dir / "project.json").is_file():
        raise WebappError(f"нет {project_dir / 'project.json'}")

    scripts_dir = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, str(scripts_dir / "text_stage.py"),
           "--project", str(project_dir), "--stage", stage_id]
    if episode:
        cmd += ["--episode", episode]
    if model:
        cmd += ["--model", model]
    if engine:
        cmd += ["--engine", engine]
    if request.strip():
        cmd += ["--request", request.strip()]

    try:
        return runner.start(cmd, {"kind": "text", "project": project,
                                  "episode": episode, "stage": stage_id})
    except TaskBusyError as e:
        raise WebappError(str(e)) from None
