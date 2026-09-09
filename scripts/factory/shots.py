"""shots.json — машиночитаемый план съёмки (спека §8).

Решение пользователя 2026-06-12: инвариант сцепки отрезков отменён.
Видео может содержать переходы между сценами, где start-кадр нового отрезка
НЕ совпадает с end-кадром предыдущего. Это сознательное отступление от спеки
§4/§8 — отрезки могут соединять ЛЮБЫЕ существующие кадры, их может быть
меньше N-1 (и даже 0).

Актуальные инварианты отрезков:
- номера отрезков 1..M без пропусков (пустой список допустим);
- start_frame обязателен и должен ссылаться на существующий кадр;
- end_frame НЕОБЯЗАТЕЛЕН; если задан — тоже должен ссылаться на существующий кадр;
- start_frame == end_frame допустим (статичный план; поведение на стороне видеомодели);

Отрезок без end_frame — движение ВНУТРИ одного плана: видеомодель получает только
первый кадр и никуда не интерполирует. Пара кадров РАЗНЫХ планов заставляет её
перетекать из локации в локацию — живой прогон 2026-09-03 дал дом, вырастающий
из ниоткуда, и лампу, чинящуюся саму. Стык планов — работа монтажа, а не
видеомодели, поэтому end_frame ставят только там, где оба кадра принадлежат
одному плану и переход между ними физически непрерывен.
- prompt непустой.
"""
from __future__ import annotations

import json
from pathlib import Path

from factory.safety import inside


class ShotsError(ValueError):
    pass


# Единая конвенция путей файлов эпизода (раньше дублировалась в generate_batch.py,
# mix_audio.py и assemble.py — теперь источник один). Меняешь схему — только тут.
def segment_path(episode_dir: Path, n: int) -> Path:
    """Путь к файлу видеоотрезка №n (`episodes/<ep>/segments/NNN.mp4`)."""
    return Path(episode_dir) / "segments" / f"{n:03d}.mp4"


def frame_path(episode_dir: Path, n: int) -> Path:
    """Путь к файлу кадра раскадровки №n (`episodes/<ep>/storyboard/NNN.png`)."""
    return Path(episode_dir) / "storyboard" / f"{n:03d}.png"


def stills_mode(shots: dict) -> bool:
    """Эпизод из кадров под озвучку: отрезков в плане нет вовсе.

    ЕДИНСТВЕННЫЙ ответ на вопрос «какой это режим» — и он свойство ПЛАНА, а не
    флага проекта. Флаг `visual_mode` говорит стадии раскадровки, что писать;
    дальше по конвейеру спрашивают уже написанное. Читателей четверо (приёмка,
    валидатор плана звука, смета, монтажный лист), и пока монтаж со сметой
    смотрели на флаг, а приёмка — на план, расхождение давало несобираемое:
    render требовал принятых отрезков, а лист собирался из кадров
    (ревью конвейера 2026-09-09).
    """
    return not (shots.get("segments") or [])


def load_shots(path: Path, project_dir: Path, episode: str | None = None) -> dict:
    """Загрузить и проверить план съёмки эпизода.

    Всё, что мешает загрузить план, поднимается своим типом ошибки: вызывающий
    код ловит ShotsError и отвечает кодом возврата, а не трейсбеком (D-4 первого
    живого прогона). Отсутствующий файл и битый JSON — такая же непригодность
    входных данных, как нарушенный инвариант.

    `episode` — серия, для которой план читают. Совпадение с полем `episode`
    внутри файла проверяется ЗДЕСЬ, потому что из этого поля строятся id единиц
    манифеста, а файлы кладутся по каталогу серии: скопированный в ep02 план с
    `episode: ep01` оплачивал бы генерацию в манифест первой серии, а картинки
    складывал во вторую (ревью конвейера 2026-09-09).
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ShotsError(f"{path}: cannot read — {e}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ShotsError(f"{path}: not valid JSON — {e}") from None

    if not isinstance(data, dict):
        raise ShotsError(f"{path}: ждали объект, получили {type(data).__name__}")

    declared = data.get("episode")
    if not isinstance(declared, str) or not declared.strip():
        raise ShotsError(
            f"{path}: нет поля episode — по нему строятся id единиц манифеста")
    if episode is not None and declared != episode:
        raise ShotsError(
            f"{path}: план серии {declared!r}, а читают его для {episode!r} — "
            "проверь, не скопирован ли он из другой серии")

    frames = data.get("frames", [])
    try:
        frame_numbers = {f["n"] for f in frames}
    except (KeyError, TypeError) as e:
        raise ShotsError(f"frame entry missing required key: {e}") from None
    if not frames:
        raise ShotsError("shots.json has no frames")
    if frame_numbers != set(range(1, len(frames) + 1)):
        raise ShotsError("frame numbers must be 1..N without gaps")

    # Отсутствующие референсы собираются РАЗОМ, а не роняют загрузку на первом же:
    # на серии из тринадцати кадров чинить по одному — против устоявшегося в репо
    # поведения (все остальные гейты показывают список проблем целиком). Строки
    # разделены переводом строки: вызывающий печатает их по одной под своей шапкой.
    missing_refs = []
    for f in frames:
        if not f.get("prompt"):
            raise ShotsError(f"frame {f['n']}: empty prompt")
        for ref in f.get("refs", []):
            # Существование файла НЕ означает права его читать: refs уезжают
            # провайдеру — _media читает файл и base64-кодирует его в тело
            # запроса. Ссылка ../../secrets существует и проходила проверку
            # существования, отправляя чужой файл наружу (ревью безопасности
            # 2026-09-05). Сначала containment, потом существование: сообщать
            # «нет такого файла» про файл снаружи — подсказка, чего там нет.
            if not inside(project_dir, Path(project_dir) / ref):
                missing_refs.append(
                    f"frame {f['n']}: ref вне проекта: {ref}")
                continue
            if not (Path(project_dir) / ref).exists():
                missing_refs.append(f"frame {f['n']}: missing ref {ref}")
    if missing_refs:
        raise ShotsError("\n".join(missing_refs))

    segments = data.get("segments", [])

    # Проверка нумерации отрезков 1..M без пропусков
    if segments:
        try:
            seg_numbers = {s["n"] for s in segments}
        except (KeyError, TypeError) as e:
            raise ShotsError(f"segment entry missing required key: {e}") from None
        if seg_numbers != set(range(1, len(segments) + 1)):
            raise ShotsError("segment numbers must be 1..M without gaps")

    for s in segments:
        try:
            n = s["n"]
            sf = s["start_frame"]
        except KeyError as e:
            raise ShotsError(f"segment entry missing required key: {e}") from None
        if sf not in frame_numbers:
            raise ShotsError(
                f"segment {n}: start_frame {sf} references missing frame")
        # end_frame необязателен: его отсутствие — это «двигайся внутри плана».
        # Проверяем только заданный, иначе отрезок без стыка планов был бы
        # невыразим и пришлось бы снова склеивать разные локации одной моделью.
        if "end_frame" in s:
            ef = s["end_frame"]
            if ef not in frame_numbers:
                raise ShotsError(
                    f"segment {n}: end_frame {ef} references missing frame")
        if not s.get("prompt"):
            raise ShotsError(f"segment {n}: empty prompt")

    # Ключи нормализуются здесь, а не у каждого потребителя: смета, генерация и
    # монтаж читают `shots["segments"]` напрямую, и в режиме кадров отсутствие
    # ключа означало бы KeyError в трёх местах вместо пустого списка в одном.
    data["frames"] = frames
    data["segments"] = segments
    return data
