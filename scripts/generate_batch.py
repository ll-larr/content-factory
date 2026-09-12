"""Батч-генерация референсов персонажей, кадров или видеоотрезков по shots.json
(спека §8; провайдеры — FINAL §5; стадия characters — спека 2026-08-02 §9).

Запускать из корня репозитория:
  python scripts/generate_batch.py --project projects/<проект> --episode ep01 --stage characters
  python scripts/generate_batch.py --project projects/<проект> --episode ep01 --stage storyboard
  python scripts/generate_batch.py --project projects/<проект> --episode ep01 --stage segments
Флаг --yes пропускает подтверждение сметы (для тестов/автоматизации).
Референсы персонажей и кадры идут через image-провайдера проекта, отрезки — через
video-провайдера (оба задаются в project.json; дефолт — по типу контента, FINAL §4).
Успешные генерации получают статус generated и ждут ревью (scripts/review.py).

Коды выхода: 0 успех; 1 сбои/отмена; 2 отказ по контракту входных данных стадии —
модель не прошла валидацию, провайдеру не хватает конфигурации (напр. ключа),
shots.json непригоден или промпт кадра не прошёл гейт консистентности (§10:
{{style}}/{{char:...}}/refs); 3 стадия заблокирована — закрыт гейт пре-продакшна
(§5: карточка персонажа не одобрена, референс не принят ревью и т.п.) или кадры
не приняты ревью (segments).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.artifact import ArtifactError, canonical_block, load_artifact
from factory.audio_plan import (AudioPlanError, audio_unit_path, is_empty,
                                lipsync_path, load_audio_plan)
from factory.env import load_env
from factory.ffmpeg_tools import (FfmpegError, apply_voice_process,
                                  ensure_png)
from factory.manifest import Manifest, ManifestError
from factory.models import (duration_problem, find_card, validate_audio_model,
                            validate_image_model,
                            validate_video_model)
from factory.preprod import episode_cast, stage_gate
from factory.project import ProjectError, load_project
from factory.prompts import (PLACEHOLDER_ANY, PromptError, expand_prompt,
                             prompt_problems)
from factory.providers import get_provider
from factory.providers.base import ProviderError
from factory.shots import ShotsError, frame_path, load_shots, segment_path

KNOWLEDGE_DIR = Path("knowledge")  # относительный путь — запуск из корня репо

# Стадии звука и роли моделей, которые каждая из них использует. Стадия audio
# делает три вида единиц сразу, потому что все три зависят только от плана и ни
# от чего больше; foley и lipsync вынесены отдельно — им нужны готовые отрезки,
# а lipsync ещё и готовый голос.
AUDIO_STAGES = {
    "audio": ("tts", "music", "sfx"),
    "foley": ("foley",),
    "lipsync": ("lipsync",),
}
_ROLE_BY_LIST = {"voice_lines": "tts", "music_cues": "music", "sfx": "sfx"}


def _validation_gate(problems: list[str]) -> int:
    """Единый вывод + код 2 для всех гейтов трат ДО сметы: и валидация карточки
    (validate_video_model/validate_image_model), и провайдерский хук
    (preflight_problems — ревью-находка: смета не должна обещать цену, которую
    submit не может выполнить) используют один и тот же формат сообщения —
    пользователь видит одинаковую картину независимо от того, какая именно
    проверка остановила прогон.

    Шапка говорит про проверку, а не про модель: тем же путём отбивается
    отсутствующий ключ провайдера (D-2), и «модель не прошла валидацию» послало
    бы человека чинить карточку вместо окружения."""
    print("ПРОВЕРКА ПЕРЕД ТРАТАМИ НЕ ПРОЙДЕНА — генерация не запущена:")
    for p in problems:
        print(f"  - {p}")
    return 2


def _tts_text(entry: dict) -> str:
    """Реплика для TTS: подача и текст через ТИРЕ.

    Разделитель не косметика: живая проба 2026-09-04 сравнила запятую и тире на
    одной и той же реплике — с тире модель читает ровнее и спокойнее. Разметки
    внутри текста нет и быть не может: теги вида <sigh> модель читает вслух.
    """
    direction = (entry.get("direction") or "").strip()
    return f"{direction} — {entry['text']}" if direction else entry["text"]


def _audio_language(card: dict, project) -> str | None:
    """Код языка в том виде, в каком его хочет КОНКРЕТНАЯ модель.

    Соответствие живёт в карточке (`language_map`), а не в коде: у gemini это
    «Russian (Russia)», у qwen3 — «Russian», и знать разницу должен тот же
    источник, что знает имена полей.
    """
    return (card.get("language_map") or {}).get(project.language)


def build_audio_jobs(stage: str, plan: dict, shots: dict, project,
                     episode_dir: Path) -> list[dict]:
    """Задания стадий звука (дизайн 2026-09-04 §5)."""
    ep = shots["episode"]
    jobs: list[dict] = []

    def card_for(role: str) -> dict:
        return find_card(KNOWLEDGE_DIR, project.audio_model(role))

    if stage == "audio":
        for list_name, role in _ROLE_BY_LIST.items():
            for entry in plan.get(list_name, []):
                model = project.audio_model(role)
                params: dict = {"tier": project.audio_tier(role)}
                if role == "tts":
                    params["text"] = _tts_text(entry)
                    params["voice"] = entry["voice"]
                    language = _audio_language(card_for(role), project)
                    if language:
                        params["language"] = language
                else:
                    params["prompt"] = entry["prompt"]
                    params["duration"] = entry["duration"]
                job = {
                    "item_id": f"{ep}/audio/{entry['id']}",
                    "kind": "audio_unit",
                    "model": model,
                    "dest": audio_unit_path(episode_dir, entry["id"]),
                    "params": params,
                }
                if role == "tts" and entry.get("process"):
                    job["process"] = entry["process"]
                jobs.append(job)
        return jobs

    if stage == "foley":
        for entry in plan.get("foley", []):
            jobs.append({
                "item_id": f"{ep}/foley/{entry['id']}",
                "kind": "foley",
                "model": project.audio_model("foley"),
                "dest": audio_unit_path(episode_dir, entry["id"], ext="mp4"),
                "params": {
                    "prompt": entry["prompt"],
                    "video": str(segment_path(episode_dir, entry["segment"])),
                    # Длительность фоли задаёт сам отрезок, а не план: дорожка
                    # короче отрезка оставила бы дыру, длиннее — залезла бы на
                    # следующий план.
                    "duration": project.segment_seconds,
                    "tier": project.audio_tier("foley"),
                },
            })
        return jobs

    # lipsync: отрезки тех реплик, где лицо в кадре и человек попросил синхрон
    for entry in plan.get("voice_lines", []):
        if not entry.get("lipsync"):
            continue
        jobs.append({
            "item_id": f"{ep}/lipsync/{entry['segment']:03d}",
            "kind": "lipsync",
            "model": project.audio_model("lipsync"),
            "dest": lipsync_path(episode_dir, entry["segment"]),
            "params": {
                "video": str(segment_path(episode_dir, entry["segment"])),
                "audio": str(audio_unit_path(episode_dir, entry["id"])),
                "tier": project.audio_tier("lipsync"),
            },
        })
    return jobs


def build_jobs(stage: str, shots: dict | None, project, episode_dir: Path,
               project_dir: Path) -> list[dict]:
    aspect = project.aspect
    jobs = []
    if stage == "characters":
        # Референсы — по составу ИМЕННО этой серии (episode_cast), а не по всем
        # карточкам bible/characters/: карточка персонажа из другой серии не
        # должна ни блокировать эту, ни оплачиваться повторно (поправка 2 задачи
        # 6; та же логика, что уже применена в preprod._cast_problems).
        # shots для этой стадии не нужен и не загружается (episode здесь берём из
        # имени папки эпизода) — этап 5 (characters) в спеке §8 предшествует
        # этапу 6 (storyboard), который только и производит shots.json, поэтому
        # на момент запуска этой стадии файла может ещё не существовать.
        # Стиль проекта обязан быть и в референсе персонажа, не только в кадрах.
        # Живой прогон 2026-09-02: без него модель нарисовала фотореалистичный
        # 3D-рендер там, где style-guide требует плоский мультфильм для детей.
        # Референс — визуальный якорь, на который ссылается КАЖДЫЙ кадр
        # раскадровки (shots.json: refs), поэтому якорь не в том стиле портит
        # весь эпизод, а не одну картинку. Источник стиля тот же, что у кадров, —
        # canonical:style в bible/style-guide.md; второго источника не заводим.
        style = canonical_block(
            project_dir / "bible" / "style-guide.md", "style")
        stray_style = PLACEHOLDER_ANY.findall(style)
        if stray_style:
            raise PromptError(
                f"style-guide.md: в canonical:style остались плейсхолдеры "
                f"{stray_style!r} — они уехали бы провайдеру буквально")
        for name in episode_cast(project_dir, episode_dir.name):
            card = project_dir / "bible" / "characters" / f"{name}.md"
            appearance = canonical_block(card, "appearance")
            # В отличие от кадров раскадровки, appearance здесь не проходит
            # expand_prompt (плейсхолдеры внутри канонического блока разворачивать
            # некому — это и есть сам канонический текст), поэтому свой чек нужен:
            # без него {{...}}, случайно оставшийся в карточке персонажа, уехал бы
            # провайдеру буквально и оплатился бы мусором.
            stray = PLACEHOLDER_ANY.findall(appearance)
            if stray:
                raise PromptError(
                    f"{card.name}: в canonical:appearance остались плейсхолдеры "
                    f"{stray!r} — они уехали бы провайдеру буквально")
            jobs.append({
                "item_id": f"bible/characters/{name}",
                "kind": "character_ref",
                "model": project.image_model,
                "dest": card.with_name(f"{name}-ref.png"),
                # Хеш карточки снимается ЗДЕСЬ, до трат, а не после скачивания:
                # во-первых, привязывать референс надо к тому тексту, по которому
                # принято решение генерировать; во-вторых, чтение файла внутри
                # try с сетевым сабмитом ниже роняло бы ArtifactError мимо
                # `except (ProviderError, FfmpegError)` — уже ОПЛАЧЕННЫЙ кадр
                # остался бы без записи в манифесте (находка финального ревью).
                "card_sha": load_artifact(card).sha,
                "params": {
                    # Стиль первым — тот же порядок, что в промптах кадров
                    # ({{style}} стоит в начале строки shots.json).
                    "prompt": f"{style} character sheet, three angles, "
                              f"neutral background. {appearance}",
                    "refs": [], "aspect_ratio": aspect,
                    "resolution": project.resolution, "tier": project.image_tier,
                },
            })
        return jobs

    ep = shots["episode"]
    if stage == "storyboard":
        for f in shots["frames"]:
            # refs в shots.json — относительно папки проекта; передаём
            # абсолютные/CWD-совместимые пути.
            resolved_refs = [str(project_dir / ref) for ref in f.get("refs", [])]
            expanded = expand_prompt(f["prompt"], project_dir)
            jobs.append({
                "item_id": f"{ep}/storyboard/{f['n']:03d}",
                "kind": "frame",
                "model": project.image_model,
                "dest": frame_path(episode_dir, f["n"]),
                "params": {"prompt": expanded, "refs": resolved_refs,
                           "aspect_ratio": aspect, "resolution": project.resolution,
                           "tier": project.image_tier},
            })
    else:  # segments
        for s in shots["segments"]:
            params = {
                "prompt": s["prompt"],
                "start_frame": str(frame_path(episode_dir, s["start_frame"])),
                "duration": project.segment_seconds,
                "aspect_ratio": aspect,
                "resolution": project.resolution,
                "tier": project.video_tier,
            }
            # Ключ end_frame появляется в params, ТОЛЬКО если он есть в плане:
            # адаптеры отличают «стык планов» от «движения внутри плана» по
            # наличию ключа (`if params.get("end_frame")`), а не по значению.
            if "end_frame" in s:
                params["end_frame"] = str(frame_path(episode_dir, s["end_frame"]))
            jobs.append({
                "item_id": f"{ep}/segments/{s['n']:03d}",
                "kind": "segment",
                "model": project.video_model,
                "dest": segment_path(episode_dir, s["n"]),
                "params": params,
            })
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--stage", required=True,
                    choices=["storyboard", "segments", "characters",
                             "audio", "foley", "lipsync"])
    ap.add_argument("--yes", action="store_true",
                    help="не спрашивать подтверждение сметы")
    args = ap.parse_args(argv)
    # Ключи из .env рядом с корнем: на чужой машине это единственный способ
    # задать их, не воюя с системными переменными окружения.
    load_env(Path(__file__).resolve().parent.parent)

    project_dir = Path(args.project)
    try:
        project = load_project(project_dir / "project.json")
    except (ProjectError, OSError) as e:
        # Непригодный бриф — отказ по контракту входных данных (код 2), как и
        # непригодный shots.json. Раньше отсюда летел трейсбек, а код возврата
        # получался 1 «технический сбой» — то есть ошибка конфигурации выглядела
        # сбоем генерации (тот же класс, что D-4 первого живого прогона).
        return _validation_gate([f"project.json: {e}"])
    episode_dir = project_dir / "episodes" / args.episode
    manifest = Manifest(project_dir / "manifest.json")

    aspect = project.aspect

    # Гейт первой половины (спека §5/§9) — ПЕРЕД загрузкой shots.json. Гейт
    # объясняет, чего не хватает по этапам («сначала прими референсы»), а
    # load_shots видит только следствие — отсутствующий на диске файл референса.
    # В обратном порядке объяснение недостижимо: до него не доходит выполнение
    # (D-5 первого живого прогона). Тот же гейт, что у factory.py check: для
    # characters он смотрит состав серии через episode_cast, а не на то, что
    # лежит в bible/characters/ (поправка 1 задачи 6); для storyboard — ещё и
    # принятость референсов.
    if args.stage in ("characters", "storyboard"):
        problems = stage_gate(project_dir, args.stage, args.episode)
        if problems:
            print(f"ГЕЙТ ЗАКРЫТ — стадия {args.stage} недоступна:")
            for p in problems:
                print(f"  - {p}")
            return 3

    # shots.json грузим только там, где он нужен: этап characters (спека §8)
    # предшествует этапу storyboard, который его производит, — на момент запуска
    # characters файла может ещё не существовать.
    shots = None
    if args.stage in ("storyboard", "segments", *AUDIO_STAGES):
        try:
            shots = load_shots(episode_dir / "shots.json", project_dir,
                               args.episode)
        except ShotsError as e:
            # Непригодный план съёмки — ошибка контракта входных данных стадии,
            # значит код 2 и сообщение, а не трейсбек и не код 1 «техсбой»
            # (D-4). Строки разделены переводом строки: load_shots собирает все
            # отсутствующие refs разом, печатаем их списком, как все гейты.
            print("ПЛАН СЪЁМКИ НЕ ПРОШЁЛ ПРОВЕРКУ — генерация не запущена:")
            for line in str(e).splitlines():
                print(f"  - {line}")
            return 2

    if args.stage in AUDIO_STAGES:
        try:
            plan = load_audio_plan(episode_dir / "audio.json", shots)
        except FileNotFoundError:
            print("ПЛАНА ЗВУКА НЕТ — генерация не запущена:")
            print(f"  - {episode_dir / 'audio.json'} не существует; "
                  f"план пишет /factory-audio")
            return 2
        except AudioPlanError as e:
            print("ПЛАН ЗВУКА НЕ ПРОШЁЛ ПРОВЕРКУ — генерация не запущена:")
            for line in str(e).splitlines():
                print(f"  - {line}")
            return 2
        if is_empty(plan):
            print("План звука пуст — нечего делать.")
            return 0

        # Роли этой стадии должны жить у ОДНОГО провайдера: цикл генерации ниже
        # работает с одним клиентом, и молча взять первого попавшегося значило бы
        # слать запросы одной модели по адресу другой.
        roles = AUDIO_STAGES[args.stage]
        problems = []
        providers_used = set()
        for role in roles:
            try:
                model, provider_name, tier = project._audio_entry(role)
            except ProjectError as e:
                problems.append(str(e))
                continue
            providers_used.add(provider_name)
            problems += validate_audio_model(
                find_card(KNOWLEDGE_DIR, model), provider_name, audio_kind=role)
        if problems:
            return _validation_gate(problems)
        if len(providers_used) > 1:
            return _validation_gate([
                f"стадия {args.stage}: роли {list(roles)} объявлены у разных "
                f"провайдеров {sorted(providers_used)} — одна стадия ходит к одному"])
        provider_name = providers_used.pop()

        # Отрезки нужны фоли и липсинку как ВХОД: генерировать дорожку по
        # непринятому отрезку значит платить за то, что человек может отклонить.
        if args.stage in ("foley", "lipsync"):
            accepted = {"done", "accepted_with_notes"}
            need = sorted({e["segment"] for e in plan.get("foley", [])} if
                          args.stage == "foley" else
                          {e["segment"] for e in plan.get("voice_lines", [])
                           if e.get("lipsync")})
            bad = {}
            for n in need:
                seg_id = f"{shots['episode']}/segments/{n:03d}"
                try:
                    status = manifest.get(seg_id)["status"]
                except ManifestError:
                    bad[seg_id] = "не генерировался"
                    continue
                if status not in accepted:
                    bad[seg_id] = f"статус {status}"
            if bad:
                print(f"ОТРЕЗКИ НЕ ПРИНЯТЫ РЕВЬЮ — стадия {args.stage} заблокирована:")
                for seg_id in sorted(bad):
                    print(f"  - {seg_id}: {bad[seg_id]}")
                return 3

        # Липсинку нужен ещё и готовый голос: он его вход, а не спутник.
        if args.stage == "lipsync":
            missing = [e["id"] for e in plan.get("voice_lines", [])
                       if e.get("lipsync")
                       and not audio_unit_path(episode_dir, e["id"]).exists()]
            if missing:
                print("РЕПЛИКИ ЕЩЁ НЕ ОЗВУЧЕНЫ — стадия lipsync заблокирована:")
                for uid in missing:
                    print(f"  - {uid}: нет файла голоса (сначала стадия audio)")
                return 3

        provider = get_provider(provider_name, KNOWLEDGE_DIR)
        jobs = build_audio_jobs(args.stage, plan, shots, project, episode_dir)
        for j in jobs:
            j["dest"].parent.mkdir(parents=True, exist_ok=True)
        return _run_jobs(jobs, manifest, provider, provider_name, project, args)

    if args.stage == "segments":
        provider_name = project.video_provider
        # Спека §6: валидация модели ПОД ВЫБРАННОГО провайдера ДО трат.
        # Поддержка end-кадра спрашивается у ПЛАНА: `end_frame` необязателен
        # (решение 2026-09-03), и модель без стыка кадров годится для плана,
        # где стыков нет. План здесь уже прочитан, поэтому вопрос задаётся
        # ровно там, где на него есть ответ.
        card = find_card(KNOWLEDGE_DIR, project.video_model)
        needs_end = any("end_frame" in s for s in shots["segments"])
        problems = validate_video_model(card, project.segment_seconds,
                                        provider_name, needs_end_frame=needs_end)
        if problems:
            return _validation_gate(problems)

        # Ревью-находка: смета не должна обещать цену, которую submit не
        # выполнит (напр. Runware не умеет resolution проекта) — провайдерский
        # хук проверяется здесь же, ДО сметы, тем же кодом 2.
        provider = get_provider(provider_name, KNOWLEDGE_DIR)
        problems = provider.preflight_problems(project.video_model, {
            "resolution": project.resolution, "aspect_ratio": aspect,
            "duration": project.segment_seconds, "tier": project.video_tier,
        })
        if problems:
            return _validation_gate(problems)

        # Чекпоинт ревью (спека ревью §4.3): отрезки строятся только на
        # принятых кадрах — done или accepted_with_notes.
        accepted = {"done", "accepted_with_notes"}
        frame_problems = {}
        for s in shots["segments"]:
            # end_frame необязателен (движение внутри плана) — проверяем те кадры,
            # что отрезок реально использует, иначе гейт падал бы KeyError на
            # корректном плане.
            used = [s["start_frame"]]
            if "end_frame" in s:
                used.append(s["end_frame"])
            for n in used:
                frame_id = f"{shots['episode']}/storyboard/{n:03d}"
                if frame_id in frame_problems:
                    continue
                try:
                    status = manifest.get(frame_id)["status"]
                except ManifestError:
                    frame_problems[frame_id] = "не генерировался"
                    continue
                if status not in accepted:
                    frame_problems[frame_id] = f"статус {status}"
        if frame_problems:
            print("КАДРЫ НЕ ПРИНЯТЫ РЕВЬЮ — стадия segments заблокирована:")
            for frame_id in sorted(frame_problems):
                print(f"  - {frame_id}: {frame_problems[frame_id]}")
            return 3

        # Промпты движения плейсхолдеры НЕ разворачивают: композицию задают кадры,
        # описывать в отрезке внешность заново незачем. Но раз не разворачивают —
        # случайно вписанный {{style}} уехал бы провайдеру буквально и оплатился
        # мусором. Отбиваем до сметы (ревью-находка задачи 5).
        stray = []
        for s in shots["segments"]:
            for junk in PLACEHOLDER_ANY.findall(s["prompt"]):
                stray.append(f"отрезок {s['n']:03d}: {junk!r}")
        if stray:
            print("ПЛЕЙСХОЛДЕРЫ В ПРОМПТЕ ДВИЖЕНИЯ — генерация не запущена "
                  "(отрезки их не разворачивают):")
            for p in stray:
                print(f"  - {p}")
            return 2
    else:
        provider_name = project.image_provider

        # Чекпоинт консистентности (спека §9) — принятость референсов состава
        # серии — часть stage_gate("storyboard"), проверен выше вместе с остальным
        # гейтом: пока он жил только здесь, factory.py check на том же состоянии
        # отвечал «гейт открыт» (D-3).

        # Гейт трат раскадровки (симметрично video): валидация image-модели под
        # выбранного провайдера ДО сметы — skeleton/не-тот-провайдер → код 2.
        card = find_card(KNOWLEDGE_DIR, project.image_model)
        # Референсы спрашиваются у ПЛАНА по той же причине, что и стык кадров у
        # видео: модель без входных картинок годится для кадра без канона и не
        # годится для лица сериала — решает не модель, а то, что в плане.
        needs_refs = args.stage == "storyboard" and any(
            f.get("refs") for f in shots["frames"])
        problems = validate_image_model(card, provider_name,
                                        needs_refs=needs_refs)
        if problems:
            return _validation_gate(problems)

        # Ревью-находка, симметрично segments: провайдерский хук ДО сметы.
        provider = get_provider(provider_name, KNOWLEDGE_DIR)
        problems = provider.preflight_problems(project.image_model, {
            "resolution": project.resolution, "aspect_ratio": aspect,
            "tier": project.image_tier,
        })
        if problems:
            return _validation_gate(problems)

        # Гейт консистентности (спека §10): негодный промпт — {{style}} не
        # объявлен, {{char:...}} без карточки/одобрения/референса, неизвестный
        # плейсхолдер — отбиваем ДО сметы. Иначе кадр без референса персонажа
        # оплатится и придёт неконсистентным.
        if args.stage == "storyboard":
            bad = []
            for f in shots["frames"]:
                for problem in prompt_problems(f["prompt"], project_dir,
                                               f.get("refs", [])):
                    bad.append(f"кадр {f['n']:03d}: {problem}")
            if bad:
                print("ПРОМПТЫ НЕ ПРОШЛИ ПРОВЕРКУ — генерация не запущена:")
                for p in bad:
                    print(f"  - {p}")
                return 2

    try:
        jobs = build_jobs(args.stage, shots, project, episode_dir, project_dir)
    except (PromptError, ArtifactError) as e:
        # Последний рубеж: гейты выше ловят известные причины, но развернуть
        # плейсхолдер может помешать и то, чего они не знают. Внятный код, а не
        # трейсбек (находка финального ревью). ArtifactError — отсюда же:
        # canonical_block живёт в factory.artifact и ошибку поднимает свою.
        return _validation_gate([f"не удалось развернуть промпт: {e}"])
    return _run_jobs(jobs, manifest, provider, provider_name, project, args)


def _run_jobs(jobs: list[dict], manifest, provider, provider_name: str,
              project, args) -> int:
    """Общий цикл выполнения заданий: манифест, цикл ревью, смета, генерация.

    Вынесен из main(), когда стадий стало шесть: копия этого цикла под звук
    означала бы две разные трактовки лимита отклонений и потолка бюджета —
    а расходятся такие копии молча и всегда.
    """
    for j in jobs:
        manifest.add(j["item_id"], kind=j["kind"])
    manifest.save()

    # Восстановление после прерванного прогона: generating → pending.
    recovered = False
    for j in jobs:
        if manifest.get(j["item_id"])["status"] == "generating":
            manifest.set_status(j["item_id"], "pending")
            recovered = True
    if recovered:
        manifest.save()

    # Цикл ревью (спека ревью §4.2): отклонённые — на перегенерацию, пока не
    # исчерпан лимит max_rejections; дальше — решение человека (review.py requeue).
    blocked = []
    requeued = False
    for j in jobs:
        item = manifest.get(j["item_id"])
        if item["status"] != "rejected":
            continue
        if item.get("reject_count", 0) < project.max_rejections:
            manifest.set_status(j["item_id"], "pending")
            requeued = True
        else:
            blocked.append(j["item_id"])
    if requeued:
        manifest.save()
    if blocked:
        print(f"ЛИМИТ ОТКЛОНЕНИЙ ИСЧЕРПАН (max_rejections="
              f"{project.max_rejections}) — требуется решение человека:")
        for item_id in blocked:
            it = manifest.get(item_id)
            print(f"  - {item_id}: reject_count={it.get('reject_count', 0)}, "
                  f"последняя причина: {it.get('reject_reason')}")

    todo = [j for j in jobs
            if manifest.get(j["item_id"])["status"] == "pending"]
    if not todo:
        awaiting = [j["item_id"] for j in jobs
                    if manifest.get(j["item_id"])["status"] == "generated"]
        if awaiting:
            print(f"Генерация не требуется; {len(awaiting)} единиц ждут ревью "
                  f"(scripts/review.py):")
            for item_id in awaiting:
                print(f"  - {item_id}")
        else:
            print("Всё уже сгенерировано — нечего делать.")
        return 0

    # provider уже создан выше (рядом с preflight-хуком) — переиспользуем.

    # Длиннее, чем модель умеет за один вызов, — отказ ДО сметы. Проверяем по
    # СОБРАННЫМ заданиям: длительность лежит в их параметрах, и одно место
    # закрывает все стадии сразу. Провайдер отбивал такое по факту запроса, то
    # есть смета обещала цену невыполнимой работы (живой прогон 2026-09-11).
    too_long = []
    for j in todo:
        seconds = j["params"].get("duration")
        if seconds is None:
            continue
        problem = duration_problem(
            find_card(KNOWLEDGE_DIR, j["model"]), provider_name, float(seconds))
        if problem:
            too_long.append(f"{j['item_id']}: {problem}")
    if too_long:
        return _validation_gate(
            too_long + ["план правится стадией audio_plan: разбей единицу "
                        "на несколько или укороти"])

    # Спека §8 шаг 2: смета перед запуском (бесплатно, до трат)
    estimates = {j["item_id"]: provider.estimate(j["model"], j["params"])
                 for j in todo}
    total = sum(estimates.values())
    models_used = ", ".join(sorted({j["model"] for j in todo}))
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.4f} {provider.unit} "
          f"({args.stage}, провайдер {provider_name}, модели: {models_used}).")
    # Потолок бюджета проверяет КОД, а не скилл: автономный запуск идёт с --yes,
    # и любая пропущенная инструкция означала бы трату мимо потолка (находка
    # финального ревью).
    #
    # Применяется он ВСЕГДА, когда задан, а не только при `autonomy: full`
    # (решение пользователя 2026-09-09): человек, поставивший потолок и
    # работающий вручную, раньше молча его не получал. Обязательным для
    # автономного режима потолок быть перестал — тормозом там стала смета всего
    # прогона с подтверждением перед стартом, а требование выдумать число
    # только мешало включить режим.
    budget = project.raw.get("budget_usd")
    if budget is not None:
        remainder = float(budget) - manifest.credits_total()
        if total > remainder:
            print(f"БЮДЖЕТ ИСЧЕРПАН: смета {total:.4f} > остаток {remainder:.4f} "
                  f"(потолок {float(budget):.4f}, потрачено "
                  f"{manifest.credits_total():.4f}). Батч не урезаем — остановка.")
            return 3

    if not args.yes:
        if input("Запустить? [y/N] ").strip().lower() != "y":
            print("Отменено.")
            return 1

    ok = fail = 0
    for j in todo:
        item = manifest.get(j["item_id"])
        manifest.set_status(j["item_id"], "generating")
        item["attempts"] += 1
        manifest.save()
        job_id = None
        try:
            job_id = provider.submit(j["model"], j["params"])
            provider.wait(job_id)
            provider.download(job_id, j["dest"])
            if j.get("process"):
                # Обработка на месте: во временный файл и подмена. Держать рядом
                # исходную и обработанную реплику незачем — монтаж берёт одну, а
                # две одноимённые дорожки однажды перепутают.
                tmp = j["dest"].with_name(j["dest"].stem + "-raw" + j["dest"].suffix)
                j["dest"].replace(tmp)
                try:
                    apply_voice_process(tmp, j["dest"], j["process"])
                except (FfmpegError, OSError):
                    # Возвращаем ОПЛАЧЕННЫЙ исходник на место и только потом
                    # пробрасываем: безусловный unlink в finally уничтожал его,
                    # статус уходил в pending без учёта трат, и следующий запуск
                    # платил за ту же реплику второй раз (ревью 2026-09-05).
                    # Симметрично ensure_png, где восстановление уже сделано так.
                    tmp.replace(j["dest"])
                    raise
                tmp.unlink(missing_ok=True)
            if j["kind"] in ("frame", "character_ref"):
                # провайдер может отдать JPEG под именем .png — нормализуем
                # (референс персонажа — такой же скачанный PNG-файл, как кадр)
                ensure_png(j["dest"])
            # Референс — единственный платный артефакт первой половины. Без
            # привязки к карточке правка внешности после приёмки не делает
            # картинку устаревшей, и кадры идут по описанию, которого уже нет
            # (находка ревью 2026-08-02). Хеш снят в build_jobs, до трат.
            extra = ({"card_sha": j["card_sha"]}
                     if j["kind"] == "character_ref" else {})
            manifest.set_status(
                j["item_id"], "generated", file=str(j["dest"]), job_id=job_id,
                prompt_sent=j["params"].get("prompt"),
                credits_spent=item["credits_spent"] + estimates[j["item_id"]],
                **extra)
            ok += 1
        except (ProviderError, FfmpegError) as e:
            # технический сбой (провайдер или конвертация ensure_png) -> вернуть
            # в очередь (спека §13); если job_id известен — сохраняем для
            # соотнесения с логами провайдера
            extra = {"job_id": job_id} if job_id is not None else {}
            manifest.set_status(j["item_id"], "pending", **extra)
            print(f"  ! {j['item_id']}: {e}")
            fail += 1
        manifest.save()

    print(f"ИТОГ: сгенерировано {ok} (ждут ревью), сбоев {fail}; "
          f"всего по проекту потрачено {manifest.credits_total():.4f} {provider.unit}.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    # Защита от кириллицы в --help на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
