"""shots.json — машиночитаемый план съёмки (спека §8).

Инвариант ТЗ: end-кадр отрезка N = start-кадр отрезка N+1
(отрезок 1 = кадры 1->2, отрезок 2 = кадры 2->3, ...).
"""
from __future__ import annotations

import json
from pathlib import Path


class ShotsError(ValueError):
    pass


def load_shots(path: Path, project_dir: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    frames = data.get("frames", [])
    try:
        numbers = {f["n"] for f in frames}
    except (KeyError, TypeError) as e:
        raise ShotsError(f"frame entry missing required key: {e}") from None
    if not frames:
        raise ShotsError("shots.json has no frames")
    if numbers != set(range(1, len(frames) + 1)):
        raise ShotsError("frame numbers must be 1..N without gaps")

    for f in frames:
        if not f.get("prompt"):
            raise ShotsError(f"frame {f['n']}: empty prompt")
        for ref in f.get("refs", []):
            if not (Path(project_dir) / ref).exists():
                raise ShotsError(f"frame {f['n']}: missing ref {ref}")

    segments = data.get("segments", [])
    for s in segments:
        try:
            expected = (s["n"], s["n"] + 1)
            actual = (s["start_frame"], s["end_frame"])
        except KeyError as e:
            raise ShotsError(f"segment entry missing required key: {e}") from None
        if actual != expected:
            raise ShotsError(
                f"segment {s['n']}: must chain frames "
                f"{expected[0]}->{expected[1]}, "
                f"got {actual[0]}->{actual[1]}")
        if not s.get("prompt"):
            raise ShotsError(f"segment {s['n']}: empty prompt")

    if len(segments) != len(frames) - 1:
        raise ShotsError(
            f"{len(frames)} frames require {len(frames) - 1} segments, "
            f"got {len(segments)}")
    return data
