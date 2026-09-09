"""Смета остатка работ по эпизоду — числами, а не печатью.

Раньше расчёт жил внутри `factory.py estimate` и сразу печатался. Панели нужны
те же числа, и единственный способ не завести вторую, слегка иную смету — вынести
расчёт сюда. CLI стал печаталкой поверх этой функции.

Смета складывает то, что ЕЩЁ предстоит: сгенерированное и принятое не считается,
платить второй раз за принятый кадр не придётся.
"""
from __future__ import annotations

from pathlib import Path

from factory.audio_plan import load_audio_plan
from factory.manifest import Manifest, ManifestError
from factory.models import ModelError
from factory.project import ProjectError, load_project
from factory.providers import get_provider
from factory.shots import ShotsError, load_shots, stills_mode

KNOWLEDGE_DIR = Path("knowledge")

# Статусы, за которые платить больше не нужно. `generated` тоже здесь: работа
# сделана и ждёт человека, а не машину.
PAID_FOR = {"done", "accepted_with_notes", "generated"}


class EstimateError(ValueError):
    """Смету не посчитать: негодные входные данные эпизода."""


# --- прогноз до раскадровки ------------------------------------------------
#
# Смета выше считает ФАКТ: сколько единиц в плане и почём. Прогноз отвечает на
# другой вопрос — «во сколько обойдётся готовое видео», — и задают его ДО того,
# как план написан. Считать его можно, потому что всё нужное в брифе уже есть:
# длительность серии, число серий, длительность отрезка и выбранные модели.
#
# Числа ниже — ДОПУЩЕНИЯ ПЛАНИРОВЩИКА, а не замеры, и они называются человеку
# вслух (`assumptions` в ответе). Врать точностью тут хуже, чем не отвечать:
# прогноз — нижняя граница, «от ~$X», и по ходу он растёт.

# Сколько держится кадр в режиме stills. Настоящую длительность задаёт реплика,
# к нему привязанная, и меряет её монтаж; здесь — оценка сверху по числу
# кадров, то есть снизу по цене.
FORECAST_STILL_SECONDS = 20

# Средняя длина реплики диктора. TTS платится ЗА ВЫЗОВ, поэтому цена зависит от
# числа реплик, а не от секунд: реплика в 12 секунд — обычная фраза-другая.
FORECAST_LINE_SECONDS = 12


def forecast(project_dir: Path | str,
             knowledge_dir: Path | str = KNOWLEDGE_DIR) -> dict:
    """Во сколько обойдётся весь проект по брифу — до всякой раскадровки.

    Возвращает ту же форму, что и `episode_estimate`, плюс `assumptions`:
    строки о том, из чего собран расчёт. Музыка, эффекты и фоли в прогноз НЕ
    входят — их в плане может не быть вовсе, и включать их в нижнюю границу
    значило бы завысить её.
    """
    project_dir = Path(project_dir)
    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        raise EstimateError(f"непригодный project.json: {e}") from None

    episodes = int(project.raw.get("episodes") or 1)
    seconds = project.raw.get("episode_duration_sec") or project.raw.get("duration_sec")
    if not seconds:
        raise EstimateError(
            "в брифе нет длительности серии — прогнозировать нечего")
    seconds = int(seconds)

    stills = project.visual_mode == "stills"
    rows: list[dict] = []
    problems: list[str] = []
    assumptions = [
        f"{episodes} × {seconds} с из брифа",
        f"реплика диктора ≈ {FORECAST_LINE_SECONDS} с (TTS платится за вызов)",
    ]

    if stills:
        frames = _ceil_div(seconds, FORECAST_STILL_SECONDS) * episodes
        segments = 0
        assumptions.append(f"кадр держится ≈ {FORECAST_STILL_SECONDS} с")
    else:
        segments = _ceil_div(seconds, project.segment_seconds) * episodes
        # По кадру на отрезок: отрезку нужен стартовый кадр, а стык планов
        # делает монтаж (`end_frame` по умолчанию не ставится).
        frames = segments
        assumptions.append(
            f"отрезок {project.segment_seconds} с, по кадру на отрезок")

    if frames:
        _add_row(rows, problems, "storyboard", frames, lambda: _unit(
            project.image_provider, project.image_model, knowledge_dir,
            {"resolution": project.resolution, "tier": project.image_tier}))
    if segments:
        _add_row(rows, problems, "segments", segments, lambda: _unit(
            project.video_provider, project.video_model, knowledge_dir,
            {"resolution": project.resolution, "tier": project.video_tier,
             "duration": project.segment_seconds}))

    lines = _ceil_div(seconds, FORECAST_LINE_SECONDS) * episodes
    _add_row(rows, problems, "voice_lines", lines, lambda: _unit(
        project.audio_provider("tts"), project.audio_model("tts"), knowledge_dir,
        {"tier": project.audio_tier("tts"), "duration": 0}))

    return {"rows": rows, "total": sum(r["cost"] for r in rows),
            "problems": problems, "assumptions": assumptions,
            "episodes": episodes}


def _ceil_div(value: int, by: int) -> int:
    return -(-int(value) // int(by))


def _unit(provider_name: str, model: str, knowledge_dir, params: dict) -> float:
    return get_provider(provider_name, knowledge_dir).estimate(model, params)


def _add_row(rows: list[dict], problems: list[str], stage: str, count: int,
             unit) -> None:
    """Строка прогноза; несчитаемая роль уходит в problems, а не роняет ответ.

    Ровно та же дисциплина, что и в смете: человек должен увидеть и цену
    известного, и список неизвестного.
    """
    try:
        rows.append({"stage": stage, "count": count, "cost": count * unit()})
    except (ProjectError, ModelError, ValueError) as e:
        problems.append(f"{stage}: {e}")


def episode_estimate(project_dir: Path | str, episode: str,
                     knowledge_dir: Path | str = KNOWLEDGE_DIR) -> dict:
    """Что осталось снять в эпизоде и во сколько это обойдётся.

    Возвращает `{"rows": [{"stage", "count", "cost"}], "total": float,
    "budget": {"limit", "spent", "left"} | None, "problems": [str]}`.

    `problems` — то, что помешало посчитать отдельную строку (не открыта карточка
    модели, роль не сконфигурирована). Это не повод отказать во всей смете:
    человек должен увидеть и цену известного, и список неизвестного.
    """
    project_dir = Path(project_dir)
    episode_dir = project_dir / "episodes" / episode

    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError, ValueError) as e:
        raise EstimateError(f"непригодный project.json: {e}") from None

    try:
        shots = load_shots(episode_dir / "shots.json", project_dir, episode)
    except (ShotsError, OSError) as e:
        raise EstimateError(f"нет пригодного shots.json: {e}") from None

    manifest = Manifest(project_dir / "manifest.json")
    problems: list[str] = []

    def pending(item_id: str) -> bool:
        try:
            return manifest.get(item_id)["status"] not in PAID_FOR
        except ManifestError:
            return True

    rows: list[dict] = []

    frames = [f for f in shots["frames"]
              if pending(f"{episode}/storyboard/{f['n']:03d}")]
    if frames:
        try:
            provider = get_provider(project.image_provider, knowledge_dir)
            unit = provider.estimate(project.image_model,
                                     {"resolution": project.resolution,
                                      "tier": project.image_tier})
            rows.append({"stage": "storyboard", "count": len(frames),
                         "cost": len(frames) * unit})
        except (ProjectError, ModelError, ValueError) as e:
            problems.append(f"кадры: {e}")

    # В режиме кадров отрезки не снимаются вовсе: эпизод собирается из кадров
    # под озвучку. Это дешевле съёмки примерно в десять раз и для познавательного
    # жанра — норма, а не экономия.
    segments = [] if stills_mode(shots) else [
        s for s in shots["segments"]
        if pending(f"{episode}/segments/{s['n']:03d}")]
    if segments:
        try:
            provider = get_provider(project.video_provider, knowledge_dir)
            unit = provider.estimate(project.video_model,
                                     {"resolution": project.resolution,
                                      "tier": project.video_tier,
                                      "duration": project.segment_seconds})
            rows.append({"stage": "segments", "count": len(segments),
                         "cost": len(segments) * unit})
        except (ProjectError, ModelError, ValueError) as e:
            problems.append(f"отрезки: {e}")

    audio_file = episode_dir / "audio.json"
    if audio_file.exists():
        try:
            plan = load_audio_plan(audio_file, shots)
        except (ValueError, OSError) as e:
            problems.append(f"план звука непригоден: {e}")
            plan = None
        if plan is not None:
            rows.extend(_audio_rows(plan, project, episode, pending,
                                    knowledge_dir, problems))

    total = sum(row["cost"] for row in rows)

    budget = None
    limit = project.raw.get("budget_usd")
    if limit is not None:
        spent = manifest.credits_total()
        budget = {"limit": float(limit), "spent": spent,
                  "left": float(limit) - spent}

    return {"rows": rows, "total": total, "budget": budget, "problems": problems}


def _lipsync_allowed(project) -> bool:
    """Допускает ли жанр липсинк.

    Карточка жанра — единственный источник ответа; смета обязана совпадать с
    гейтом, иначе человек увидит цену того, что запущено не будет.
    """
    from factory.genres import GenreError

    try:
        return bool(project.genre_card()["lipsync"])
    except (GenreError, OSError):
        return True


def _audio_rows(plan: dict, project, episode: str, pending, knowledge_dir,
                problems: list[str]) -> list[dict]:
    """Строки сметы по звуку: реплики, музыка, эффекты, фоли и липсинк."""
    rows: list[dict] = []

    for list_name, role, prefix in (("voice_lines", "tts", "audio"),
                                    ("music_cues", "music", "audio"),
                                    ("sfx", "sfx", "audio"),
                                    ("foley", "foley", "foley")):
        entries = [e for e in plan.get(list_name, [])
                   if pending(f"{episode}/{prefix}/{e['id']}")]
        if not entries:
            continue
        try:
            model = project.audio_model(role)
            provider = get_provider(project.audio_provider(role), knowledge_dir)
        except (ProjectError, ModelError) as e:
            problems.append(f"{list_name}: {e}")
            continue
        # Длительность обязана попасть в смету: эффекты и музыка на WaveSpeed
        # тарифицируются ПОСЕКУНДНО (замер 2026-09-05), и счёт по числу единиц
        # занизил смету эпизода впятеро — $0.19 против $1.04 списанных.
        # У реплик длительности нет: TTS платится за вызов.
        try:
            cost = sum(provider.estimate(model,
                                         {"tier": project.audio_tier(role),
                                          "duration": e.get("duration", 0)})
                       for e in entries)
        except (ModelError, ValueError) as e:
            problems.append(f"{list_name}: {e}")
            continue
        rows.append({"stage": list_name, "count": len(entries), "cost": cost})

    lip = [e for e in plan.get("voice_lines", [])
           if e.get("lipsync") and pending(f"{episode}/lipsync/{e['segment']:03d}")]
    if lip and not _lipsync_allowed(project):
        problems.append("липсинк не считается: жанр его не допускает")
        lip = []
    if lip:
        try:
            model = project.audio_model("lipsync")
            provider = get_provider(project.audio_provider("lipsync"), knowledge_dir)
            unit = provider.estimate(model, {"tier": project.audio_tier("lipsync")})
            rows.append({"stage": "lipsync", "count": len(lip),
                         "cost": len(lip) * unit})
        except (ProjectError, ModelError, ValueError) as e:
            problems.append(f"lipsync: {e}")

    return rows
