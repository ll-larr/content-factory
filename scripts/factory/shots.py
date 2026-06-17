"""shots.json — машиночитаемый план съёмки (спека §8).

Решение пользователя 2026-06-12: инвариант сцепки отрезков отменён.
Видео может содержать переходы между сценами, где start-кадр нового отрезка
НЕ совпадает с end-кадром предыдущего. Это сознательное отступление от спеки
§4/§8 — отрезки могут соединять ЛЮБЫЕ существующие кадры, их может быть
меньше N-1 (и даже 0).

Актуальные инварианты отрезков:
- номера отрезков 1..M без пропусков (пустой список допустим);
- start_frame и end_frame каждого отрезка должны ссылаться на существующие кадры;
- start_frame == end_frame допустим (статичный план; поведение на стороне видеомодели);
- prompt непустой.
"""
from __future__ import annotations

import json
from pathlib import Path


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


def load_shots(path: Path, project_dir: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    frames = data.get("frames", [])
    try:
        frame_numbers = {f["n"] for f in frames}
    except (KeyError, TypeError) as e:
        raise ShotsError(f"frame entry missing required key: {e}") from None
    if not frames:
        raise ShotsError("shots.json has no frames")
    if frame_numbers != set(range(1, len(frames) + 1)):
        raise ShotsError("frame numbers must be 1..N without gaps")

    for f in frames:
        if not f.get("prompt"):
            raise ShotsError(f"frame {f['n']}: empty prompt")
        for ref in f.get("refs", []):
            if not (Path(project_dir) / ref).exists():
                raise ShotsError(f"frame {f['n']}: missing ref {ref}")

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
            ef = s["end_frame"]
        except KeyError as e:
            raise ShotsError(f"segment entry missing required key: {e}") from None
        if sf not in frame_numbers:
            raise ShotsError(
                f"segment {n}: start_frame {sf} references missing frame")
        if ef not in frame_numbers:
            raise ShotsError(
                f"segment {n}: end_frame {ef} references missing frame")
        if not s.get("prompt"):
            raise ShotsError(f"segment {n}: empty prompt")

    return data
