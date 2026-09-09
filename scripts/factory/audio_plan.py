"""audio.json — план звука эпизода (спека фазы 2 §4, дизайн 2026-09-04 §3).

Аналог shots.json: единственный источник правды о репликах, музыке, эффектах и
фоли. Тайминг: segment (номер отрезка из shots.json) + offset (сек от начала
отрезка); абсолютные таймкоды вычисляет сведение по фактическим длительностям
файлов отрезков.

Четыре списка:
- ``voice_lines`` — реплики: speaker, voice (ПРЕСЕТ голоса модели), text;
  необязательные ``direction`` (подача) и ``lipsync``;
- ``music_cues``, ``sfx`` — промпт и длительность;
- ``foley`` — дорожка фактуры по готовому отрезку: промпт есть, длительности НЕТ
  (её задаёт сам отрезок), по одной записи на отрезок.

Разделение ``voice`` и ``direction`` — следствие живых проб 2026-09-04. Личность
голоса живёт в карточке персонажа и не меняется весь сезон; подача своя у каждой
реплики. В одном поле правка интонации одной сцены уехала бы в тембр персонажа.

Единица ``voice_lines`` — реплика ЦЕЛИКОМ, а не слово: подряд идущие повторы
(«Мало. Мало. Мало.») TTS читает одинаково даже с прямым указанием, а собирать
фразу из отдельно сгенерированных слов нельзя — тембр между вызовами гуляет.
"""
from __future__ import annotations

import json
from pathlib import Path

from factory.ffmpeg_tools import VOICE_PROCESSES
from factory.safety import is_safe_name

REQUIRED_BY_LIST = {
    "voice_lines": ("speaker", "voice", "text"),
    "music_cues": ("prompt",),
    "sfx": ("prompt",),
    "foley": ("prompt",),
}
NEEDS_DURATION = {"music_cues", "sfx"}

# Потолок уровня в огибающей. 2.0 — это +6 dB: усиление вдвое ещё осмысленно,
# а всё, что выше, почти всегда опечатка (перепутанные проценты с долями).
_MAX_LEVEL = 2.0


class AudioPlanError(ValueError):
    pass


# Единая конвенция путей звука — источник один, как segment_path в shots.py.
def audio_unit_path(episode_dir, unit_id: str, ext: str = "mp3"):
    """Файл аудио-единицы (`episodes/<ep>/audio/<id>.<ext>`)."""
    return Path(episode_dir) / "audio" / f"{unit_id}.{ext}"


def lipsync_path(episode_dir, n: int):
    """Отрезок после липсинка (`episodes/<ep>/segments/NNN-lipsync.mp4`).

    Отдельный файл, а НЕ перезапись исходника: неудачный липсинк не должен
    уничтожать оплаченное видео, а монтаж выбирает между ними по приёмке.
    """
    return Path(episode_dir) / "segments" / f"{n:03d}-lipsync.mp4"


def _check_number(eid: str, name: str, value, minimum, strict: bool) -> float:
    bad = (isinstance(value, bool) or not isinstance(value, (int, float))
           or (value <= minimum if strict else value < minimum))
    if bad:
        op = ">" if strict else ">="
        raise AudioPlanError(f"{eid}: {name} must be a number {op} {minimum}")
    return float(value)


def _check_envelope(eid: str, value) -> list[list[float]]:
    """Огибающая громкости: [[t, level], ...], t не убывает, level в 0..2.

    Точки читаются по порядку и не сортируются: непорядок почти всегда опечатка,
    а молчаливая сортировка тихо поменяла бы авторский замысел громкости.
    """
    if not isinstance(value, list) or not value:
        raise AudioPlanError(f"{eid}: envelope must be a non-empty list of [t, level]")
    prev_t = None
    points: list[list[float]] = []
    for point in value:
        if (isinstance(point, (str, bytes)) or not isinstance(point, (list, tuple))
                or len(point) != 2):
            raise AudioPlanError(f"{eid}: envelope point must be [t, level], got {point!r}")
        t, level = point
        for name, v in (("t", t), ("level", level)):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise AudioPlanError(f"{eid}: envelope {name} must be a number, got {v!r}")
        if t < 0:
            raise AudioPlanError(f"{eid}: envelope t must be >= 0, got {t!r}")
        if prev_t is not None and t < prev_t:
            raise AudioPlanError(
                f"{eid}: envelope time goes backwards ({prev_t} -> {t})")
        if not 0 <= level <= _MAX_LEVEL:
            raise AudioPlanError(
                f"{eid}: envelope level must be within 0..{_MAX_LEVEL}, got {level!r}")
        prev_t = t
        points.append([float(t), float(level)])
    return points


def _plan_units(shots: dict) -> tuple[set[int], str]:
    """К чему привязаны координаты плана звука: к отрезкам или к кадрам.

    В режиме `stills` отрезков нет вовсе — единицей эпизода становится КАДР, и
    поле `segment` реплики указывает на него (`montage/src/stills.ts`: «в этом
    режиме сегмент и есть кадр»). Валидатор об этом не знал и сверял номера
    только с отрезками, поэтому ЛЮБОЙ план звука в режиме кадров отбивался
    целиком, а с ним и весь режим: тесты строили монтажный лист из готового
    плана и через загрузчик не проходили (найдено дымовым прогоном 2026-09-08).

    Решение по отсутствию отрезков, а не по флагу проекта: `shots` — это всё,
    что здесь известно, а второй источник правды о режиме означал бы два ответа
    на один вопрос.
    """
    from factory.shots import stills_mode

    if stills_mode(shots):
        return {f["n"] for f in shots.get("frames") or []}, "frame"
    return {s["n"] for s in shots["segments"]}, "segment"


def load_audio_plan(path: Path, shots: dict) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    seg_numbers, unit = _plan_units(shots)

    seen_ids: set[str] = set()
    for list_name, required in REQUIRED_BY_LIST.items():
        for entry in data.get(list_name, []):
            eid = entry.get("id")
            if not eid:
                raise AudioPlanError(f"{list_name}: entry without id")
            if eid in seen_ids:
                raise AudioPlanError(f"duplicate id: {eid!r}")
            # id становится именем файла (audio_unit_path), поэтому обязан быть
            # ОДНИМ компонентом пути. Без этого запись уходила за пределы
            # проекта: download создаёт каталоги и подменяет файл по любому
            # пути, а лишний ../ в данных плана превращал генерацию звука в
            # запись куда угодно (ревью безопасности 2026-09-05).
            if not is_safe_name(eid):
                raise AudioPlanError(
                    f"{eid!r}: id must be a single path component "
                    r"(no '/', '\', '..' or drive letters)")
            seen_ids.add(eid)
            for field in required:
                if not entry.get(field):
                    raise AudioPlanError(f"{eid}: empty or missing {field!r}")
            if list_name in NEEDS_DURATION:
                _check_number(eid, "duration", entry.get("duration"), 0, True)
            seg = entry.get("segment")
            if seg is None:
                raise AudioPlanError(f"{eid}: missing 'segment'")
            if seg not in seg_numbers:
                raise AudioPlanError(
                    f"{eid}: segment {seg!r} references missing {unit} "
                    f"(есть: {sorted(seg_numbers) or 'ни одного'})")
            entry["offset"] = _check_number(
                eid, "offset", entry.get("offset", 0), 0, False)
            if "envelope" in entry:
                entry["envelope"] = _check_envelope(eid, entry["envelope"])
            if list_name == "sfx":
                # Подложка и событие — разные слои микса: подложка звучит
                # непрерывно и обязана быть заметно тише речи, событие звучит
                # мгновение и должно быть слышно. Отличить их по длительности
                # нельзя (пятисекундный гудок — событие), поэтому флаг явный.
                entry["ambience"] = bool(entry.get("ambience", False))
            if list_name == "voice_lines":
                entry.setdefault("direction", None)
                entry["lipsync"] = bool(entry.get("lipsync", False))
                # Обработка голоса именуется, а не описывается: одинаковый
                # результат во всех сериях важнее гибкости. Опечатку ловим здесь,
                # иначе она всплыла бы после ОПЛАЧЕННОЙ генерации.
                process = entry.setdefault("process", None)
                if process is not None and process not in VOICE_PROCESSES:
                    raise AudioPlanError(
                        f"{eid}: unknown process {process!r}; "
                        f"known: {sorted(VOICE_PROCESSES)}")

    # Фоли — дорожка НА ОТРЕЗОК: две дорожки на один отрезок звучали бы
    # одновременно и глушили друг друга, а какая из них лишняя — знает только
    # человек. Отказ здесь честнее молчаливого выбора первой попавшейся.
    seen_segments: set = set()
    for entry in data.get("foley", []):
        seg = entry["segment"]
        if seg in seen_segments:
            raise AudioPlanError(
                f"foley: segment {seg} has more than one track")
        seen_segments.add(seg)

    # Липсинк адресуется ОТРЕЗКОМ, а не идентификатором реплики: и файл
    # (`NNN-lipsync.mp4`), и единица манифеста именуются номером отрезка.
    # Две реплики с lipsync на одном отрезке дали бы два задания с одинаковым
    # адресом: первое платит и пишет файл, второе падает необработанным
    # ManifestError уже ПОСЛЕ траты (ревью 2026-09-05). Та же причина, по
    # которой одна дорожка фоли на отрезок.
    seen_lipsync: set = set()
    for entry in data.get("voice_lines", []):
        if not entry.get("lipsync"):
            continue
        seg = entry["segment"]
        if seg in seen_lipsync:
            raise AudioPlanError(
                f"voice_lines: segment {seg} has more than one lipsync entry — "
                "липсинк адресуется отрезком, двум репликам одного отрезка "
                "нужен один общий дубль")
        seen_lipsync.add(seg)

    for list_name in REQUIRED_BY_LIST:
        data.setdefault(list_name, [])
    return data


def is_empty(plan: dict) -> bool:
    return not any(plan[k] for k in REQUIRED_BY_LIST)
