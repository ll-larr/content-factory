"""Монтажный лист — контракт между Python и Remotion (спека 2026-08-31 §4).

Python передаёт НАМЕРЕНИЕ: какие файлы, в каком порядке, с каким смещением внутри
отрезка и с какой громкостью. Факты о медиа (длительности, fps, размеры) выясняет
Remotion через `parseMedia` и сам раскладывает намерение в кадры.

Поэтому в этом модуле НЕТ ни одного обращения к ffprobe и ни одной длительности:
если бы их писал Python, обе стороны читали бы те же файлы разными способами и
однажды разошлись бы в ответе.

Координаты `segment` + `offset` — те же, что в `audio.json`; модуль их не трогает.
Пути в листе — относительные к каталогу проекта, который отдаётся рендеру
как `--public-dir`.
"""
from __future__ import annotations

from pathlib import Path

from factory.audio_plan import load_audio_plan
from factory.manifest import ManifestError

# Принято ревью — то же множество, что было в assemble.py и mix_audio.py.
ACCEPTED = {"done", "accepted_with_notes"}

# Громкости дорожек (перенесены дословно из mix_audio.py).
VOICE_VOLUME = 1.0
# Событийный эффект: слышен мгновение, поэтому громкий. Подложка — наоборот:
# она звучит непрерывно, и уровень события для неё означает, что речь под ней
# не разобрать (живой прогон 2026-09-05: море на 0.7 перекрыло все реплики).
SFX_VOLUME = 0.40
AMBIENCE_VOLUME = 0.09
MUSIC_VOLUME = 0.14
# Фоли — фактура под всем остальным: шаги и жесть не должны спорить с событийным
# SFX, у которого своя драматургическая роль. Тише SFX, громче музыки.
FOLEY_VOLUME = 0.5

# Приглушение музыки под речью и SFX. Прежде — фильтр ffmpeg
# `sidechaincompress=threshold=0.01:ratio=20:attack=5:release=1050`, выбранный
# пользователем на слух из семи вариантов (живая калибровка 2026-09-02); суммарное приглушение
# выбранного варианта относительно недакнутой подложки — −6.3 dB.
#
# В Remotion компрессора нет, и он не нужен: компрессор угадывает по амплитуде,
# где речь, а мы знаем это точно из самого листа. Переносим как огибающую:
# gain — во сколько раз падает музыка под речью, attack/release — длины рамп входа
# и выхода. Числа рамп не догадка: 5 мс потому, что длиннее музыка «наезжает» на
# первый слог; 1050 мс потому, что короче между фразами слышно «дыхание» громкости.
#
# ВАЖНО про gain. Записанные в прежних доках «−6.3 dB» — это СРЕДНЕЕ приглушение по
# файлу, а не мгновенная глубина, и брать их сюда напрямую нельзя. Замер продакнутой
# музыки отдельно от речи (2026-09-02) дал у старого фильтра мгновенные −10.2, −13.5
# и −23.0 dB на трёх репликах: `ratio=20` давит тем сильнее, чем громче речь.
# Постоянной глубиной такое не воспроизвести, поэтому её выбрали так же, как
# выбирали исходные семь вариантов, — на слух. Пользователь 2026-09-02 прослушал
# пробы на −8, −10, −12 и −14 dB и выбрал −12 dB: 10^(-12/20) = 0.2512.
#
# ПЕРЕСМОТРЕНО 2026-09-05 после первого эпизода со звуком. Пользователь: «дакинг
# очень явный и звучит плохо». Глубина уполовинена по децибелам (−12 → −6 dB,
# 10^(-6/20) = 0.5), но главное не в ней: слышимый рывок давала АТАКА. Пять
# миллисекунд при 24 fps — это 0.12 кадра, то есть громкость падала целиком
# внутри одного кадра, ступенькой. Такую ступеньку ухо слышит как «подсос»
# независимо от глубины. Атака растянута до 120 мс (около трёх кадров), спад
# укорочен до 700 мс: длинный спад держал музыку внизу между фразами и делал
# движение уровня заметным само по себе.
# ПРОБА 2026-09-06: подавление ВЫКЛЮЧЕНО (gain 1.0 = уровень не меняется).
# Смысл пробы: при подложке на 0.09 и музыке на 0.14 речь может выигрывать сама,
# без движения уровня — а любое движение уровня слышно и потому спорно.
# Механизм оставлен на месте: включить обратно значит вернуть одно число.
DUCK_GAIN = 1.0
DUCK_ATTACK_MS = 120
DUCK_RELEASE_MS = 700

# Режим кадров: сколько кадр висит, если к нему не привязано ни одной реплики,
# и сколько длится перекрытие между соседними. Секунды здесь — НАМЕРЕНИЕ, а не
# факт о медиа: настоящую длительность реплики измеряет parseMedia в монтаже,
# Python аудиофайлы не открывает.
STILL_MIN_SECONDS = 3.0
STILL_TAIL_SECONDS = 0.6
STILL_CROSSFADE_SECONDS = 0.4
# Медленный наезд: во сколько раз кадр увеличивается за своё время на экране.
# Больше — заметно как движение и отвлекает от смысла; меньше — не читается.
STILL_ZOOM = 1.08

# Допуск контроля длительности (спека §12 базовой спеки).
DURATION_TOLERANCE = 0.05

FORMATS = ("16x9", "9x16")   # соответствие форматам проекта — ASPECT_FORMAT ниже

# Оформление шортсов по умолчанию: тёмный нейтральный фон с тёплым акцентом.
# Не спорит ни с одной палитрой кадра и читается на телефоне. Формат 9:16 обязан
# работать без единой строчки настройки (решение пользователя 2026-09-02), блок
# `shorts` в project.json — только переопределение.
DEFAULT_BACKGROUND = "#101820"
DEFAULT_ACCENT = "#E8B04B"

# Разделители, по первому из которых тема проекта обрезается до баннера.
BANNER_SEPARATORS = (":", "—", "–", " - ")


# Дорожки микшера и их громкости по умолчанию. Числа выше — не настройки «на
# вкус», а результат живых прослушиваний, и комментарии к ним стоят рядом с
# самими числами. Проект может их переопределить блоком `mix` в project.json;
# отсутствие блока означает «как решили на слух», а не «ноль».
TRACKS = ("voice", "sfx", "ambience", "music", "foley")
DEFAULT_VOLUMES = {
    "voice": VOICE_VOLUME, "sfx": SFX_VOLUME, "ambience": AMBIENCE_VOLUME,
    "music": MUSIC_VOLUME, "foley": FOLEY_VOLUME,
}
TRACK_LABELS = {
    "voice": "Речь", "sfx": "Эффекты", "ambience": "Подложка",
    "music": "Музыка", "foley": "Фоли",
}

# Потолок громкости дорожки. Выше единицы поднимать можно (тихая запись бывает),
# но вдвое — уже клиппинг, а мастеринг потом честно прижмёт весь эпизод.
MAX_VOLUME = 2.0


class MontageError(ValueError):
    """Лист не собрать: отказ по контракту входных данных, не трейсбек."""


# Формат проекта → композиция монтажа. Единственное место соответствия: до
# 2026-09-08 его не было вовсе, `render.py` брал формат из флага с дефолтом
# «16x9», и вертикальный проект молча собирался горизонтальным — кадры
# приходили 9:16, а рамка оставалась 16:9.
ASPECT_FORMAT = {"16:9": "16x9", "9:16": "9x16"}


def captions_on(project, fmt: str,
                knowledge_dir: Path | str = "knowledge") -> bool:
    """Показывать ли субтитры в этой сборке. Решает КАРТОЧКА ЖАНРА.

    `captions` объявлялся в карточках с 2026-09-07 и не читался никем: субтитры
    рисовались всегда и только в 9:16, зашитым решением внутри композиции.
    У познавательного жанра в карточке стоит `always`, и обещание не работало —
    именно его смотрят без звука чаще всего.

    Непрочитанная карточка — не повод молча включить или выключить: остаётся
    прежнее поведение (шортс с субтитрами, горизонталь без них), потому что
    оно совпадает с `shorts_only`, а это дефолт трёх жанров из четырёх.
    """
    from factory.genres import GenreError

    try:
        mode = project.genre_card(knowledge_dir)["captions"]
    except (GenreError, KeyError, OSError, ValueError):
        mode = "shorts_only"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return fmt == "9x16"


def format_for(project) -> str:
    """Формат сборки, вытекающий из брифа: его соотношение сторон.

    Флаг `--format` остаётся и перебивает это: вертикальную нарезку
    горизонтального проекта делают осознанно. Но МОЛЧАНИЕ теперь значит «как в
    проекте», а не «16x9 в любом случае».
    """
    try:
        return ASPECT_FORMAT[project.aspect]
    except KeyError:
        raise MontageError(
            f"неизвестное соотношение сторон {project.aspect!r}; "
            f"известны {sorted(ASPECT_FORMAT)}") from None


def _number(value, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MontageError(f"mix.{name}: ждали число, получено {value!r}")
    if not low <= float(value) <= high:
        raise MontageError(
            f"mix.{name}: допустимо от {low} до {high}, получено {value}")
    return float(value)


def mix_settings(project) -> dict:
    """Микшер эпизода: громкости дорожек, выключенные дорожки, дакинг, голоса.

    ЕДИНСТВЕННОЕ место, где решается, с какой громкостью что звучит: его читает
    и монтажный лист, и панель. Второго набора значений не заводить — сведение,
    которое человек слышит в панели, и сведение, которое уезжает в рендер,
    обязаны быть одним.

    Дефолты — константы этого модуля, добытые живыми прослушиваниями. Блок
    `mix` в project.json их переопределяет, и это правка ЭТОГО проекта: чужой
    сериал не должен наследовать чью-то калибровку.
    """
    raw = (getattr(project, "raw", None) or {}).get("mix") or {}
    if not isinstance(raw, dict):
        raise MontageError(f"mix: ждали объект, получено {type(raw).__name__}")

    volumes = dict(DEFAULT_VOLUMES)
    for track, value in (raw.get("volumes") or {}).items():
        if track not in TRACKS:
            raise MontageError(
                f"mix.volumes: неизвестная дорожка {track!r}; есть {list(TRACKS)}")
        volumes[track] = _number(value, f"volumes.{track}", 0.0, MAX_VOLUME)

    muted = raw.get("muted") or []
    if not isinstance(muted, list) or any(t not in TRACKS for t in muted):
        raise MontageError(
            f"mix.muted: ждали список дорожек из {list(TRACKS)}, получено {muted!r}")

    # Выключенная дорожка — это громкость ноль, а не выброшенные из листа
    # единицы: длительности эпизода она не меняет, и вернуть её обратно значит
    # снять галку, а не пересобирать лист.
    for track in muted:
        volumes[track] = 0.0

    speakers = raw.get("speakers") or {}
    if not isinstance(speakers, dict):
        raise MontageError("mix.speakers: ждали объект «имя героя: множитель»")
    speakers = {str(name): _number(value, f"speakers.{name}", 0.0, MAX_VOLUME)
                for name, value in speakers.items()}

    duck_raw = raw.get("duck") or {}
    if not isinstance(duck_raw, dict):
        raise MontageError("mix.duck: ждали объект")
    duck = {
        "gain": _number(duck_raw.get("gain", DUCK_GAIN), "duck.gain", 0.0, 1.0),
        "attackMs": _number(duck_raw.get("attack_ms", DUCK_ATTACK_MS),
                            "duck.attack_ms", 0.0, 5000.0),
        "releaseMs": _number(duck_raw.get("release_ms", DUCK_RELEASE_MS),
                             "duck.release_ms", 0.0, 5000.0),
    }

    # `target_lufs: null` — не пропуск, а выключенный мастеринг: так эпизод
    # уходит с той громкостью, которую собрал монтаж. Поле читается и из блока
    # `mix`, и из корня брифа — второе было раньше и у живых проектов осталось.
    from factory.ffmpeg_tools import DEFAULT_TARGET_LUFS
    brief = getattr(project, "raw", None) or {}
    target = raw["target_lufs"] if "target_lufs" in raw else brief.get(
        "target_lufs", DEFAULT_TARGET_LUFS)
    if target is not None:
        target = _number(target, "target_lufs", -36.0, 0.0)

    return {"volumes": volumes, "muted": list(muted), "speakers": speakers,
            "duck": duck, "target_lufs": target}


def load_plan(episode_dir: Path, shots: dict) -> dict:
    """План звука эпизода; отсутствующий audio.json — пустой план, не ошибка.

    Эпизод без звука собирается: так было в assemble.py, так остаётся. Это
    позволяет смотреть картинку до того, как готова озвучка.
    """
    path = Path(episode_dir) / "audio.json"
    if not path.exists():
        return {"voice_lines": [], "music_cues": [], "sfx": []}
    return load_audio_plan(path, shots)


def review_problems(manifest, episode: str, shots: dict,
                    plan: dict) -> dict[str, str]:
    """Единицы, не прошедшие ревью: {item_id: причина}.

    Один список на оба гейта — отрезки и звук. Раньше это были два разных
    скрипта, и человек узнавал о второй проблеме только починив первую.
    """
    problems: dict[str, str] = {}

    def check(item_id: str) -> None:
        try:
            status = manifest.get(item_id)["status"]
        except ManifestError:
            problems[item_id] = "не генерировался"
            return
        if status not in ACCEPTED:
            problems[item_id] = f"статус {status}"

    # В режиме кадров отрезков нет вовсе, и приёмку проходят КАДРЫ. Раньше
    # здесь стоял `shots["segments"]` — в таком эпизоде это KeyError, то есть
    # трейсбек вместо гейта (найдено дымовым прогоном 2026-09-08). Режим
    # определяется по самому плану съёмки: второй источник правды о нём означал
    # бы два ответа на один вопрос.
    segments = shots.get("segments") or []
    if segments:
        for seg in segments:
            check(f"{episode}/segments/{seg['n']:03d}")
    else:
        for frame in shots.get("frames") or []:
            check(f"{episode}/storyboard/{frame['n']:03d}")
    for entry in plan["voice_lines"] + plan["music_cues"] + plan["sfx"]:
        check(f"{episode}/audio/{entry['id']}")
    # Фоли живёт в манифесте под своим префиксом: дорожка по видео — отдельная
    # стадия с отдельной приёмкой, и путать её с озвучкой в одном пространстве
    # имён значило бы получать коллизии идентификаторов из разных списков плана.
    for entry in plan.get("foley", []):
        check(f"{episode}/foley/{entry['id']}")
    return problems


def banner_text(project) -> str:
    """Текст баннера шортса из брифа: тема до первого разделителя.

    У пилота «Смотрительница маяка: две серии о том…» даёт «Смотрительница маяка».
    Пустая или бессодержательная тема → имя проекта, оно есть всегда.
    """
    theme = (project.theme or "").strip()
    for sep in BANNER_SEPARATORS:
        if sep in theme:
            theme = theme.split(sep, 1)[0].strip()
            break
    return theme.strip(" —–-") or project.name


def shorts_settings(project) -> dict:
    """Оформление шортса: дефолты из брифа, поверх — блок `shorts`, если он есть."""
    raw = project.raw.get("shorts") or {}
    return {
        "banner": raw.get("banner") or banner_text(project),
        "background": raw.get("background") or DEFAULT_BACKGROUND,
        "accent": raw.get("accent") or DEFAULT_ACCENT,
    }


def _relative(project_dir: Path, path: Path, missing: list[str]) -> str:
    """Путь относительно каталога проекта (он же --public-dir рендера).

    Файл вне проекта — отказ, а не тихая абсолютная ссылка: рендер получает
    каталог проекта и физически не сможет достать то, что лежит снаружи.
    """
    project_dir = Path(project_dir).resolve()
    path = Path(path).resolve()
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        raise MontageError(
            f"файл вне каталога проекта, рендер его не увидит: {path}") from None
    if not path.exists():
        missing.append(str(path))
    return rel.as_posix()


def _audio_track(entries, kind_volume: float, manifest, episode: str,
                 project_dir: Path, missing: list[str],
                 with_text: bool, prefix: str = "audio",
                 speakers: dict | None = None) -> list[dict]:
    """Дорожка монтажного листа. `speakers` — множитель громкости по герою.

    Множитель именно множитель, а не замена: дорожка речи остаётся одной, у неё
    общая громкость, а герой отклоняется от неё. Иначе выключить всю речь разом
    стало бы невозможно.
    """
    track = []
    for entry in entries:
        item_id = f"{episode}/{prefix}/{entry['id']}"
        try:
            item = manifest.get(item_id)
        except ManifestError as exc:
            raise MontageError(str(exc)) from None
        file = item.get("file")
        if not file:
            raise MontageError(f"{item_id}: в манифесте нет пути к файлу")
        gain = (speakers or {}).get(entry.get("speaker"), 1.0)
        placed = {
            "id": entry["id"],
            "file": _relative(project_dir, Path(file), missing),
            "segment": entry["segment"],
            "offset": entry["offset"],
            "volume": kind_volume * gain,
        }
        if with_text:
            placed["text"] = entry["text"]
        # Огибающая едет как есть: она уже проверена валидатором плана, а
        # интерполяцию по кадрам делает монтаж — он один знает fps.
        if entry.get("envelope"):
            placed["envelope"] = entry["envelope"]
        track.append(placed)
    return track


def _segment_file(project_dir: Path, episode_dir: Path, episode: str, n: int,
                  manifest, missing: list[str]) -> str:
    """Файл отрезка для монтажа: липсинк, если он принят, иначе исходник.

    Липсинк пишется отдельным файлом (`NNN-lipsync.mp4`), чтобы неудачный дубль
    не уничтожал оплаченное видео. Выбор между ними делает ЗДЕСЬ Python, потому
    что состояние приёмки знает манифест; монтаж остаётся глупым и берёт то, что
    ему дали.
    """
    accepted = {"done", "accepted_with_notes"}
    lipsync = episode_dir / "segments" / f"{n:03d}-lipsync.mp4"
    try:
        item = manifest.get(f"{episode}/lipsync/{n:03d}")
    except ManifestError:
        item = None
    if item is not None and item.get("status") in accepted and lipsync.exists():
        return _relative(project_dir, lipsync, missing)
    return _relative(project_dir, episode_dir / "segments" / f"{n:03d}.mp4",
                     missing)


def _still_file(project_dir: Path, episode_dir: Path, episode: str, n: int,
                manifest, missing: list[str]) -> str:
    """Файл принятого кадра для режима кадров.

    Та же дисциплина, что у отрезков: в монтаж попадает только принятое ревью.
    Кадр, который человек ещё не смотрел, в серию не уедет.
    """
    item_id = f"{episode}/storyboard/{n:03d}"
    try:
        status = manifest.get(item_id)["status"]
    except ManifestError:
        status = None
    if status not in ACCEPTED:
        missing.append(f"{item_id}: кадр не принят ревью (статус {status or 'нет'})")
        return ""
    return _relative(project_dir, episode_dir / "storyboard" / f"{n:03d}.png",
                     missing)


def build_edit_list(project, project_dir: Path, episode: str, shots: dict,
                    manifest, fmt: str = "16x9", plan: dict | None = None,
                    knowledge_dir: Path | str = "knowledge") -> dict:
    """Собрать монтажный лист. Медиа не читает — только файловую систему.

    `knowledge_dir` нужен ради карточки жанра: она решает, показывать ли
    субтитры. Путь передаётся явно, а не берётся от текущего каталога, — иначе
    ответ зависел бы от того, откуда запустили команду.
    """
    if fmt not in FORMATS:
        raise MontageError(
            f"неизвестный формат {fmt!r}; доступны: {', '.join(FORMATS)}")

    project_dir = Path(project_dir)
    episode_dir = project_dir / "episodes" / episode
    if plan is None:
        plan = load_plan(episode_dir, shots)

    missing: list[str] = []
    mix = mix_settings(project)

    # В режиме кадров отрезков нет вовсе: эпизод собирается из принятых кадров
    # под озвучку. Требовать при этом файлы отрезков было бы требованием того,
    # что сознательно не снимали.
    stills_mode = getattr(project, "visual_mode", "video") == "stills"
    if stills_mode:
        segments = []
        stills = [
            {"n": frame["n"],
             "file": _still_file(project_dir, episode_dir, episode, frame["n"],
                                 manifest, missing)}
            for frame in sorted(shots["frames"], key=lambda f: f["n"])
        ]
    else:
        stills = []
        segments = [
            {"n": seg["n"],
             "file": _segment_file(project_dir, episode_dir, episode, seg["n"],
                                   manifest, missing)}
            for seg in sorted(shots["segments"], key=lambda s: s["n"])
        ]

    edit_list = {
        "episode": episode,
        "format": fmt,
        "mode": "stills" if stills_mode else "video",
        "segments": segments,
        "stills": stills,
        "stillsSettings": {
            "minSeconds": STILL_MIN_SECONDS,
            "tailSeconds": STILL_TAIL_SECONDS,
            "crossfadeSeconds": STILL_CROSSFADE_SECONDS,
            "zoom": STILL_ZOOM,
        },
        "voice": _audio_track(plan["voice_lines"], mix["volumes"]["voice"],
                              manifest, episode, project_dir, missing,
                              with_text=True, speakers=mix["speakers"]),
        "sfx": _audio_track([e for e in plan["sfx"] if not e.get("ambience")],
                            mix["volumes"]["sfx"], manifest, episode,
                            project_dir, missing, with_text=False),
        "ambience": _audio_track([e for e in plan["sfx"] if e.get("ambience")],
                                 mix["volumes"]["ambience"], manifest, episode,
                                 project_dir, missing, with_text=False),
        "music": _audio_track(plan["music_cues"], mix["volumes"]["music"],
                              manifest, episode, project_dir, missing,
                              with_text=False),
        "foley": _audio_track(plan.get("foley", []), mix["volumes"]["foley"],
                              manifest, episode, project_dir, missing,
                              with_text=False, prefix="foley"),
        "duck": mix["duck"],
        # Субтитры: раньше композиция 9:16 рисовала их всегда, а 16:9 не умела
        # вовсе. Теперь решает жанр, а монтаж просто слушается.
        "captions": captions_on(project, fmt, knowledge_dir),
        "expected": {"segments": len(segments),
                     "segmentSeconds": project.segment_seconds,
                     "tolerance": DURATION_TOLERANCE},
        "shorts": shorts_settings(project),
    }

    # Все отсутствующие файлы разом: чинить по одному — против устоявшегося
    # в репозитории поведения гейтов.
    if missing:
        raise MontageError(
            "файлы не найдены:\n" + "\n".join(f"  - {p}" for p in missing))
    return edit_list
