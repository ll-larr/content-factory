"""audio.json — план звука эпизода (спека фазы 2 §4).

Аналог shots.json: единственный источник правды о репликах, музыке и SFX.
Тайминг: segment (номер отрезка из shots.json) + offset (сек от начала
отрезка); абсолютные таймкоды вычисляет сведение по фактическим
длительностям файлов отрезков.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_BY_LIST = {
    "voice_lines": ("speaker", "voice", "text"),
    "music_cues": ("prompt",),
    "sfx": ("prompt",),
}
NEEDS_DURATION = {"music_cues", "sfx"}


class AudioPlanError(ValueError):
    pass


def _check_number(eid: str, name: str, value, minimum, strict: bool) -> float:
    bad = (isinstance(value, bool) or not isinstance(value, (int, float))
           or (value <= minimum if strict else value < minimum))
    if bad:
        op = ">" if strict else ">="
        raise AudioPlanError(f"{eid}: {name} must be a number {op} {minimum}")
    return float(value)


def load_audio_plan(path: Path, shots: dict) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    seg_numbers = {s["n"] for s in shots.get("segments", [])}

    seen_ids: set[str] = set()
    for list_name, required in REQUIRED_BY_LIST.items():
        for entry in data.get(list_name, []):
            eid = entry.get("id")
            if not eid:
                raise AudioPlanError(f"{list_name}: entry without id")
            if eid in seen_ids:
                raise AudioPlanError(f"duplicate id: {eid!r}")
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
                    f"{eid}: segment {seg!r} references missing segment")
            entry["offset"] = _check_number(
                eid, "offset", entry.get("offset", 0), 0, False)

    for list_name in REQUIRED_BY_LIST:
        data.setdefault(list_name, [])
    return data


def is_empty(plan: dict) -> bool:
    return not any(plan[k] for k in REQUIRED_BY_LIST)
