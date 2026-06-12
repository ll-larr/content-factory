# Фаза 2: звук и сборка — план имплементации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать этапы 8–9 конвейера: генерация звука через аудио-модели Higgsfield (Inworld TTS / Mirelo SFX / Sonilo Music), сведение дорожки и сборка финального mp4 (ffmpeg).

**Architecture:** Звук переиспользует всю инфраструктуру фазы 1 (манифест, сметы, ревью, resume) через новую стадию `audio` в generate_batch.py; план звука — `audio.json` с таймингом «отрезок+смещение»; mix_audio.py и assemble.py — обёртки над ffmpeg с гейтами ревью (exit 3). Спека: `docs/superpowers/specs/2026-06-12-phase2-sound-assembly-design.md`.

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, ffmpeg/ffprobe 8.1 (в PATH), Higgsfield CLI (`higgsfield`).

**Правила выполнения (как в фазе 1):**
- Ветка `phase-2-sound-assembly`, запуск скриптов и тестов ИЗ КОРНЯ репозитория.
- Тесты строго: `.\.venv\Scripts\python.exe -m pytest -q` (venv НЕ активировать).
- Один коммит на задачу + отдельные коммиты фиксов ревью.
- Задачи 2 и 6 тратят кредиты — выполняются в ОСНОВНОЙ сессии с пользователем (НЕ субагентом), каждая трата подтверждается.
- ffmpeg обязателен в окружении тестов (стоит через winget) — skipif НЕ ставить, отсутствие ffmpeg должно ронять тесты громко.

---

## Карта файлов

| Файл | Роль |
|---|---|
| `scripts/factory/ffmpeg_tools.py` (create, Task 1) | единственное место запуска ffmpeg/ffprobe: `run_ffmpeg`, `probe_duration`, `has_audio_stream`, `FfmpegError` |
| `scripts/assemble.py` (create Task 1, modify Task 5) | сборка: гейт отрезков → склейка → (Task 5) наложение mix.m4a → контроль ±5% |
| `tests/conftest.py` (create, Task 1) | фикстуры `make_clip` / `make_tone` — крошечные медиа через lavfi |
| `tests/test_assemble.py` (create Task 1, extend Task 5) | тесты сборки |
| `knowledge/audio/*.md` (create, Task 2) | карточки 3 аудио-моделей (продукт спайка, status: verified) |
| `scripts/factory/audio_plan.py` (create, Task 3) | загрузка/валидация audio.json, `AudioPlanError` |
| `scripts/factory/models.py` (modify, Task 3) | + `validate_audio_model()` |
| `scripts/generate_batch.py` (modify, Task 3) | + стадия `audio` |
| `tests/test_audio_plan.py`, `tests/test_models.py`, `tests/test_generate_batch.py` (Task 3) | тесты |
| `scripts/mix_audio.py` (create, Task 4) | сведение: гейт аудио → таймлайн по ffprobe → ducking → mix.m4a |
| `tests/test_mix_audio.py` (create, Task 4) | тесты сведения |
| `projects/_smoke/episodes/ep01/audio.json` (create, Task 6) | план звука для боевого smoke |

---

### Task 1: ffmpeg_tools + assemble.py (видео-only) + гейт отрезков

**Files:**
- Create: `scripts/factory/ffmpeg_tools.py`
- Create: `scripts/assemble.py`
- Create: `tests/conftest.py`
- Test: `tests/test_assemble.py`

Примечание по дизайну: склейка — единая перекодировка libx264 (надёжно при разных кодеках источников). При разных РАЗРЕШЕНИЯХ отрезков ffmpeg упадёт с понятной ошибкой — это допустимо для v1 (отрезки одного эпизода генерятся одной моделью). 16:9 наследуется от отрезков, отдельно не форсируется.

- [ ] **Step 1: Написать tests/conftest.py (общие фикстуры медиа-заглушек)**

```python
"""Общие фикстуры фазы 2: крошечные медиафайлы через ffmpeg lavfi.

ffmpeg обязателен в окружении (спека фазы 2 §10) — отсутствие роняет тесты.
"""
import subprocess
from pathlib import Path

import pytest


def _ffmpeg(args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
        check=True)


@pytest.fixture
def make_clip():
    """Видеоклип-заглушка заданной длительности (lavfi color, 64x36, 8 fps)."""
    def _make(path, seconds):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", f"color=c=red:s=64x36:r=8:d={seconds}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
        return path
    return _make


@pytest.fixture
def make_tone():
    """Аудио-заглушка (lavfi sine 440 Гц, aac) заданной длительности."""
    def _make(path, seconds):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                 "-c:a", "aac", str(path)])
        return path
    return _make
```

- [ ] **Step 2: Написать падающие тесты tests/test_assemble.py**

```python
"""Тесты assemble.py (спека фазы 2 §8): гейт отрезков, склейка, контроль ±5%."""
import json
from pathlib import Path

import pytest

import assemble
from factory.ffmpeg_tools import has_audio_stream, probe_duration
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path, monkeypatch, make_clip):
    """Проект: 2 отрезка по 5с (quality high), реальные крошечные mp4, оба done."""
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": "nano_banana_flash", "video": "kling3_0"},
    }), encoding="utf-8")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                   {"n": 3, "prompt": "c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    for n in (1, 2):
        make_clip(ep / "segments" / f"{n:03d}.mp4", 5.0)
    set_segment_statuses(pdir, "done")
    monkeypatch.chdir(tmp_path)
    return pdir


def set_segment_statuses(pdir, final_status):
    """Перезаписать манифест: оба отрезка проведены до final_status легальным путём."""
    m = Manifest(pdir / "manifest.json")
    m.data = {"items": {}}
    for n in (1, 2):
        item_id = f"ep01/segments/{n:03d}"
        m.add(item_id, kind="segment")
        m.set_status(item_id, "generating")
        m.set_status(item_id, "generated")
        if final_status == "rejected":
            m.set_status(item_id, "rejected", reject_reason="r")
        elif final_status != "generated":
            m.set_status(item_id, final_status)
    m.save()


def run(proj):
    return assemble.main(["--project", str(proj), "--episode", "ep01"])


def test_happy_path(proj, capsys):
    assert run(proj) == 0
    dest = proj / "episodes" / "ep01" / "final" / "ep01.mp4"
    assert dest.exists()
    assert abs(probe_duration(dest) - 10.0) < 0.5
    out = capsys.readouterr().out
    assert "ВНИМАНИЕ" not in out          # длительность в допуске
    assert not has_audio_stream(dest)     # Task 1: звука ещё нет


def test_atomic_no_tmp_left(proj):
    assert run(proj) == 0
    final_dir = proj / "episodes" / "ep01" / "final"
    assert list(final_dir.glob("*.tmp.*")) == []


def test_gate_blocks_unreviewed(proj, capsys):
    set_segment_statuses(proj, "generated")
    assert run(proj) == 3
    out = capsys.readouterr().out
    assert "заблокирована" in out
    assert "ep01/segments/001" in out
    assert not (proj / "episodes" / "ep01" / "final" / "ep01.mp4").exists()


def test_gate_blocks_rejected(proj, capsys):
    set_segment_statuses(proj, "rejected")
    assert run(proj) == 3
    assert "статус rejected" in capsys.readouterr().out


def test_gate_blocks_never_generated(proj, capsys):
    (proj / "manifest.json").unlink()
    assert run(proj) == 3
    assert "не генерировался" in capsys.readouterr().out


def test_accepted_with_notes_passes_gate(proj):
    set_segment_statuses(proj, "accepted_with_notes")
    assert run(proj) == 0


def test_missing_segment_file(proj, capsys):
    (proj / "episodes" / "ep01" / "segments" / "002.mp4").unlink()
    assert run(proj) == 1
    assert "не найден" in capsys.readouterr().out


def test_duration_warning(proj, make_clip, capsys):
    # Реальные клипы по 1с при плане 2×5с → вне допуска ±5%
    for n in (1, 2):
        make_clip(proj / "episodes" / "ep01" / "segments" / f"{n:03d}.mp4", 1.0)
    assert run(proj) == 0  # файл сохраняется, exit 0
    out = capsys.readouterr().out
    assert "ВНИМАНИЕ" in out
    assert (proj / "episodes" / "ep01" / "final" / "ep01.mp4").exists()


def test_no_segments_in_shots(proj, capsys):
    ep = proj / "episodes" / "ep01"
    shots = json.loads((ep / "shots.json").read_text(encoding="utf-8"))
    shots["segments"] = []
    (ep / "shots.json").write_text(json.dumps(shots), encoding="utf-8")
    assert run(proj) == 1
    assert "собирать нечего" in capsys.readouterr().out
```

- [ ] **Step 3: Запустить тесты — убедиться, что падают на импорте**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_assemble.py -q`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'assemble'` (и `factory.ffmpeg_tools`).

- [ ] **Step 4: Написать scripts/factory/ffmpeg_tools.py**

```python
"""Обёртка ffmpeg/ffprobe (спека фазы 2 §7–9).

Единственное место в кодовой базе, где запускаются бинари ffmpeg/ffprobe.
Ошибки — FfmpegError с полной командой для ручной диагностики.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


def _run(args: list[str], timeout: int = 600) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, encoding="utf-8", errors="replace",
            timeout=timeout)
    except FileNotFoundError:
        raise FfmpegError(
            f"{args[0]} не найден в PATH — установите ffmpeg (winget)") from None
    except subprocess.TimeoutExpired:
        raise FfmpegError(
            f"Команда не завершилась за {timeout}с: {args!r}") from None
    if result.returncode != 0:
        raise FfmpegError(
            f"Команда завершилась с кодом {result.returncode}: {args!r}\n"
            f"stderr: {result.stderr[-2000:]}")
    return result.stdout


def run_ffmpeg(args: list[str]) -> None:
    """Выполнить ffmpeg; args — всё после имени бинаря. Перезапись разрешена."""
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args)


def probe_duration(path: Path) -> float:
    """Длительность медиафайла в секундах (ffprobe)."""
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return float(out.strip())
    except ValueError:
        raise FfmpegError(
            f"ffprobe не вернул длительность для {path}: {out!r}") from None


def has_audio_stream(path: Path) -> bool:
    """Есть ли в файле аудиопоток."""
    out = _run(["ffprobe", "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=codec_type", "-of",
                "default=noprint_wrappers=1:nokey=1", str(path)])
    return "audio" in out
```

- [ ] **Step 5: Написать scripts/assemble.py (видео-only)**

```python
"""Сборка финального видео серии из отрезков (спека фазы 2 §8, основная §12).

Запускать из корня репозитория:
  python scripts/assemble.py --project projects/pilot --episode ep01

Гейт: все отрезки эпизода приняты ревью (done/accepted_with_notes), иначе
список + exit 3. Склейка — единая перекодировка libx264 (при разных
разрешениях отрезков ffmpeg упадёт с понятной ошибкой — допустимо для v1).
Контроль длительности: факт против len(segments)*segment_seconds, допуск ±5%
(спека §12) — при выходе предупреждение, файл сохраняется, exit 0.

Коды выхода: 0 успех; 1 ошибка данных/ffmpeg; 3 отрезки не приняты ревью.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.ffmpeg_tools import FfmpegError, probe_duration, run_ffmpeg
from factory.manifest import Manifest, ManifestError
from factory.project import load_project
from factory.shots import load_shots

ACCEPTED = {"done", "accepted_with_notes"}
DURATION_TOLERANCE = 0.05  # ±5% (спека §12)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    project = load_project(project_dir / "project.json")
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")
    ep = shots["episode"]

    segments = shots["segments"]
    if not segments:
        print("В shots.json нет отрезков — собирать нечего.")
        return 1

    # Гейт: все отрезки приняты ревью (расширение гейта фазы 1 на отрезки)
    problems = {}
    for s in segments:
        item_id = f"{ep}/segments/{s['n']:03d}"
        try:
            status = manifest.get(item_id)["status"]
        except ManifestError:
            problems[item_id] = "не генерировался"
            continue
        if status not in ACCEPTED:
            problems[item_id] = f"статус {status}"
    if problems:
        print("ОТРЕЗКИ НЕ ПРИНЯТЫ РЕВЬЮ — сборка заблокирована:")
        for item_id in sorted(problems):
            print(f"  - {item_id}: {problems[item_id]}")
        return 3

    files = []
    for s in sorted(segments, key=lambda s: s["n"]):
        f = episode_dir / "segments" / f"{s['n']:03d}.mp4"
        if not f.exists():
            print(f"Файл отрезка не найден: {f}")
            return 1
        files.append(f)

    dest = episode_dir / "final" / f"{args.episode}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.mp4")

    inputs: list[str] = []
    for f in files:
        inputs.extend(["-i", str(f)])
    n = len(files)
    filt = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    try:
        run_ffmpeg(inputs + ["-filter_complex", filt, "-map", "[v]",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1

    fact = probe_duration(dest)
    plan = len(segments) * project.segment_seconds
    if abs(fact - plan) > plan * DURATION_TOLERANCE:
        print(f"ВНИМАНИЕ: длительность {fact:.2f}с вне допуска ±5% "
              f"от плановой {plan}с — проверьте отрезки.")
    print(f"Собрано: {dest} ({fact:.2f}с, {n} отрезков, без звука).")
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [ ] **Step 6: Запустить тесты задачи — все зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_assemble.py -q`
Expected: PASS (9 passed).

- [ ] **Step 7: Полный прогон**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: 108 старых + 9 новых = 117 passed.

- [ ] **Step 8: Commit**

```bash
git add scripts/factory/ffmpeg_tools.py scripts/assemble.py tests/conftest.py tests/test_assemble.py
git commit -m "feat: assemble.py — склейка отрезков с гейтом ревью и контролем ±5% (фаза 2 Task 1)"
```

---

### Task 2: спайк аудио-моделей + карточки

**⚠ Выполняется в ОСНОВНОЙ сессии с пользователем (тратит кредиты, ~6–8 кр). Перед тратами убедиться, что кредиты пополнены (на конец фазы 1 было ~0.5 кр).**

**Files:**
- Create: `knowledge/audio/inworld_text_to_speech.md`
- Create: `knowledge/audio/mirelo_text_to_audio.md`
- Create: `knowledge/audio/sonilo_music.md`
- Modify: `knowledge/higgsfield-cli.md` (новые факты о CLI, если будут)
- Артефакты прослушивания: `spike/audio/` (в git не коммитить, если бинарники большие — записать выводы в карточки)

Уже известно из бесплатной разведки (2026-06-12, зафиксировать в карточках):
- `inworld_text_to_speech`: params `prompt` (req), `voice` (req, string); смета 2 кр, НЕ зависит от длины текста на пробах до ~350 символов; имя голоса сметой не валидируется.
- `mirelo_text_to_audio`: params `prompt`, `duration` (req); смета 1.25 кр / 5 с.
- `sonilo_music`: params `prompt`, `duration` (req); смета 1.88 кр / 30 с.

- [ ] **Step 1: Бесплатная разведка каталога голосов Inworld**

Искать в порядке: (а) `higgsfield model get inworld_text_to_speech --json` (уже смотрели — enum голосов нет); (б) справка CLI `higgsfield generate create --help`; (в) веб-UI Higgsfield (страница Speech — там выпадающий список голосов, выписать точные имена 3–5 голосов: мужской, женский, детский/характерный); (г) доки https://docs.inworld.ai (List voices API) — имена голосов Inworld TTS-1.5 (Ashley, Hades и т.п.) как кандидаты. Зафиксировать список кандидатов в карточку.

- [ ] **Step 2: Пробные cost-валидации (бесплатно)**

```powershell
higgsfield generate cost inworld_text_to_speech --prompt "<текст ~1000 символов>" --voice "Ashley" --json
higgsfield generate cost mirelo_text_to_audio --prompt "door creak" --duration 10 --json
higgsfield generate cost sonilo_music --prompt "calm theme" --duration 60 --json
higgsfield generate cost sonilo_music --prompt "calm theme" --duration 300 --json
```

Цель: скейлинг цены TTS на длинном тексте; сетки/лимиты duration у Mirelo и Sonilo (ошибка валидации укажет границы). Записать в карточки.

- [ ] **Step 3: Платные генерации (КАЖДАЯ — с подтверждением пользователя)**

План трат (~6–8 кр): 1) TTS en, короткая реплика, голос-кандидат №1 (2 кр); 2) TTS ru, та же модель, второй голос (2 кр) — проверка русского; 3) Mirelo 5 с (1.25 кр); 4) Sonilo 30 с (1.88 кр). Генерация через CLI:

```powershell
higgsfield generate create inworld_text_to_speech --prompt "Hello! I am a cartoon cat astronaut." --voice "<голос>" --json
higgsfield generate get <job_id> --json   # до status=completed, забрать result_url
```

Скачать по result_url в `spike/audio/`, прослушать с пользователем. Проверить: формат файла (расширение/кодек — важно для AUDIO_EXT в Task 3), качество, поведение невалидного voice id (одна дешёвая проба, если Step 1 не дал каталога).

- [ ] **Step 4: Написать карточки (status: verified)**

Каркас каждой карточки (заполнить фактами спайка; пример для TTS):

```markdown
---
id: inworld_text_to_speech
type: audio
family: inworld
status: verified
audio_kind: tts
output_format: mp3        # ФАКТ из спайка (поправить при необходимости)
cost_tier: low
---

# Inworld Text to Speech

## Параметры CLI
- `--prompt` — текст реплики (обязателен)
- `--voice` — id голоса (обязателен; сметой НЕ валидируется)

## Стоимость
2 кр/генерация; от длины текста не зависит (проверено до N символов — вписать).
Выгодно для длинного закадра, дорого для множества коротких реплик
(план перехода на ElevenLabs — спека фазы 2 §3).

## Голоса
(точный список проверенных голосов из спайка: id — описание — язык)

## Наблюдения
(качество en/ru, скорость генерации, формат файла, типовые ошибки)
```

Карточки `mirelo_text_to_audio` (audio_kind: sfx) и `sonilo_music` (audio_kind: music) — та же структура + поле `duration`: проверенные границы/сетка.

- [ ] **Step 5: Обновить knowledge/higgsfield-cli.md** — новые факты о контракте CLI для аудио (если отличаются от видео: формат ответа get, result_url и т.п.).

- [ ] **Step 6: Commit**

```bash
git add knowledge/audio/ knowledge/higgsfield-cli.md
git commit -m "docs: карточки аудио-моделей по результатам спайка (фаза 2 Task 2)"
```

---

### Task 3: audio_plan.py + validate_audio_model + стадия audio в generate_batch.py

**Files:**
- Create: `scripts/factory/audio_plan.py`
- Modify: `scripts/factory/models.py` (добавить `validate_audio_model` в конец файла)
- Modify: `scripts/generate_batch.py`
- Test: `tests/test_audio_plan.py` (create), `tests/test_models.py` (extend), `tests/test_generate_batch.py` (extend)

- [ ] **Step 1: Написать падающие тесты tests/test_audio_plan.py**

```python
"""Тесты audio_plan.py (спека фазы 2 §4)."""
import json
from pathlib import Path

import pytest

from factory.audio_plan import AudioPlanError, is_empty, load_audio_plan

SHOTS = {"episode": "ep01",
         "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"}],
         "segments": [{"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m"}]}

VALID = {
    "voice_lines": [{"id": "vl-01", "speaker": "cat", "voice": "Ashley",
                     "text": "Hi!", "segment": 1, "offset": 0.5}],
    "music_cues": [{"id": "mus-01", "prompt": "calm", "duration": 10,
                    "segment": 1, "offset": 0}],
    "sfx": [{"id": "sfx-01", "prompt": "creak", "duration": 3,
             "segment": 1, "offset": 1.0}],
}


def write_plan(tmp_path, data):
    p = tmp_path / "audio.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_valid_plan_loads(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, VALID), SHOTS)
    assert plan["voice_lines"][0]["id"] == "vl-01"
    assert plan["voice_lines"][0]["offset"] == 0.5
    assert not is_empty(plan)


def test_missing_lists_default_to_empty(tmp_path):
    plan = load_audio_plan(write_plan(tmp_path, {}), SHOTS)
    assert plan["voice_lines"] == []
    assert plan["music_cues"] == []
    assert plan["sfx"] == []
    assert is_empty(plan)


def test_duplicate_id_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["sfx"][0]["id"] = "vl-01"
    with pytest.raises(AudioPlanError, match="duplicate id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_missing_voice_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    del data["voice_lines"][0]["voice"]
    with pytest.raises(AudioPlanError, match="voice"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_missing_text_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["text"] = ""
    with pytest.raises(AudioPlanError, match="text"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_bad_duration_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["music_cues"][0]["duration"] = 0
    with pytest.raises(AudioPlanError, match="duration"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_unknown_segment_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["segment"] = 99
    with pytest.raises(AudioPlanError, match="segment 99"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_negative_offset_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    data["voice_lines"][0]["offset"] = -1
    with pytest.raises(AudioPlanError, match="offset"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)


def test_entry_without_id_raises(tmp_path):
    data = json.loads(json.dumps(VALID))
    del data["sfx"][0]["id"]
    with pytest.raises(AudioPlanError, match="without id"):
        load_audio_plan(write_plan(tmp_path, data), SHOTS)
```

- [ ] **Step 2: Добавить тесты validate_audio_model в tests/test_models.py (в конец файла)**

```python
def test_validate_audio_model_ok():
    from factory.models import validate_audio_model
    card = {"id": "inworld_text_to_speech", "type": "audio", "status": "verified"}
    assert validate_audio_model(card) == []


def test_validate_audio_model_wrong_type():
    from factory.models import validate_audio_model
    card = {"id": "kling3_0", "type": "video", "status": "verified"}
    assert any("not an audio model" in p for p in validate_audio_model(card))


def test_validate_audio_model_skeleton():
    from factory.models import validate_audio_model
    card = {"id": "sonilo_music", "type": "audio", "status": "skeleton"}
    assert any("skeleton" in p for p in validate_audio_model(card))
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_audio_plan.py tests/test_models.py -q`
Expected: FAIL/ERROR — `No module named 'factory.audio_plan'`, `cannot import name 'validate_audio_model'`.

- [ ] **Step 4: Написать scripts/factory/audio_plan.py**

```python
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
```

- [ ] **Step 5: Добавить validate_audio_model в конец scripts/factory/models.py**

```python
def validate_audio_model(card: dict) -> list[str]:
    """Валидация аудио-модели ДО траты кредитов (спека фазы 2 §5)."""
    problems: list[str] = []
    if card["type"] != "audio":
        problems.append(f"{card['id']}: not an audio model")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems
```

- [ ] **Step 6: Прогнать тесты Steps 1–2 — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_audio_plan.py tests/test_models.py -q`
Expected: PASS.

- [ ] **Step 7: Написать падающие тесты стадии audio (добавить в конец tests/test_generate_batch.py)**

```python
# ---- Фаза 2: стадия audio ----

AUDIO_CARD = ("---\nid: {mid}\ntype: audio\nfamily: {fam}\nstatus: verified\n"
              "cost_tier: low\n---\n# {mid}\n")


@pytest.fixture
def aproj(proj):
    """proj + аудио-модели в project.json, карточки audio и audio.json."""
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"].update({"tts": "inworld_text_to_speech",
                         "music": "sonilo_music",
                         "sfx": "mirelo_text_to_audio"})
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    kdir = Path("knowledge") / "audio"
    kdir.mkdir(parents=True, exist_ok=True)
    for mid, fam in (("inworld_text_to_speech", "inworld"),
                     ("sonilo_music", "sonilo"),
                     ("mirelo_text_to_audio", "mirelo")):
        (kdir / f"{mid}.md").write_text(
            AUDIO_CARD.format(mid=mid, fam=fam), encoding="utf-8")
    (proj / "episodes" / "ep01" / "audio.json").write_text(json.dumps({
        "voice_lines": [{"id": "vl-01", "speaker": "cat", "voice": "Ashley",
                         "text": "Hello!", "segment": 1, "offset": 0.5}],
        "music_cues": [{"id": "mus-01", "prompt": "calm space music",
                        "duration": 10, "segment": 1, "offset": 0}],
        "sfx": [{"id": "sfx-01", "prompt": "door creak", "duration": 3,
                 "segment": 2, "offset": 1.0}],
    }), encoding="utf-8")
    return proj


def run_audio(proj):
    return gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "audio", "--yes"])


def test_audio_happy_path(aproj, monkeypatch):
    calls = fake_hf(monkeypatch)
    assert run_audio(aproj) == 0
    assert len(calls["submitted"]) == 3
    m = Manifest(aproj / "manifest.json")
    assert m.get("ep01/audio/vl-01")["status"] == "generated"
    assert m.get("ep01/audio/vl-01")["kind"] == "voice"
    assert m.get("ep01/audio/mus-01")["kind"] == "music"
    assert m.get("ep01/audio/sfx-01")["kind"] == "sfx"
    ep = aproj / "episodes" / "ep01" / "audio"
    assert (ep / "voice" / "vl-01.mp3").exists()
    assert (ep / "music" / "mus-01.mp3").exists()
    assert (ep / "sfx" / "sfx-01.mp3").exists()


def test_audio_params_passed(aproj, monkeypatch):
    calls = fake_hf(monkeypatch)
    run_audio(aproj)
    voice_params = [p for p in calls["submitted"] if "voice" in p]
    assert voice_params == [{"prompt": "Hello!", "voice": "Ashley"}]
    dur_params = [p for p in calls["submitted"] if "duration" in p]
    assert {p["duration"] for p in dur_params} == {10, 3}


def test_audio_missing_plan(aproj, monkeypatch, capsys):
    (aproj / "episodes" / "ep01" / "audio.json").unlink()
    assert run_audio(aproj) == 1
    assert "audio.json" in capsys.readouterr().out


def test_audio_skeleton_card_blocks_before_estimate(aproj, monkeypatch, capsys):
    estimate_called = []
    monkeypatch.setattr(gb.hf, "estimate",
                        lambda m, p: estimate_called.append(1) or 2.0)
    card = Path("knowledge/audio/sonilo_music.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run_audio(aproj) == 2
    assert estimate_called == []
    assert "skeleton" in capsys.readouterr().out


def test_audio_missing_model_key(aproj, monkeypatch, capsys):
    pj = json.loads((aproj / "project.json").read_text(encoding="utf-8"))
    del pj["models"]["tts"]
    (aproj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    assert run_audio(aproj) == 2
    assert "models.tts" in capsys.readouterr().out


def test_audio_resume_skips_generated(aproj, monkeypatch):
    fake_hf(monkeypatch)
    run_audio(aproj)
    calls2 = fake_hf(monkeypatch)
    assert run_audio(aproj) == 0
    assert calls2["submitted"] == []


def test_audio_invalid_segment_ref_raises(aproj, monkeypatch):
    ep = aproj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"][0]["segment"] = 99
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    fake_hf(monkeypatch)
    with pytest.raises(gb.AudioPlanError):
        run_audio(aproj)
```

- [ ] **Step 8: Запустить — убедиться, что падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: новые тесты FAIL (`invalid choice: 'audio'` / `AttributeError: AudioPlanError`), старые PASS.

- [ ] **Step 9: Изменить scripts/generate_batch.py**

9a. Обновить докстринг модуля (строки 1–11) на:

```python
"""Батч-генерация кадров, видеоотрезков или аудио по shots.json/audio.json (спека §8, фаза 2 §5).

Запускать из корня репозитория:
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage storyboard
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage segments
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage audio
Флаг --yes пропускает подтверждение сметы (для тестов/автоматизации).
Успешные генерации получают статус generated и ждут ревью (scripts/review.py).

Коды выхода: 0 успех; 1 сбои/отмена/нет audio.json; 2 модель не прошла
валидацию; 3 segments заблокирован — кадры не приняты ревью.
"""
```

9b. Добавить импорт после `from factory.manifest import ...`:

```python
from factory.audio_plan import AudioPlanError, load_audio_plan
```

и заменить строку импорта models на:

```python
from factory.models import find_card, validate_audio_model, validate_video_model
```

9c. После `KNOWLEDGE_DIR = ...` добавить константы:

```python
AUDIO_EXT = ".mp3"  # формат выхода аудио-моделей Higgsfield (спайк фазы 2 Task 2)
# (список audio.json, ключ models в project.json, kind манифеста, подпапка)
AUDIO_GROUPS = (("voice_lines", "tts", "voice", "voice"),
                ("music_cues", "music", "music", "music"),
                ("sfx", "sfx", "sfx", "sfx"))
```

⚠ Если спайк (Task 2) показал другое расширение файлов — поправить AUDIO_EXT здесь.

9d. Заменить функцию `build_jobs` целиком на:

```python
def build_jobs(stage: str, shots: dict, project, episode_dir: Path,
               project_dir: Path, audio_plan: dict | None = None) -> list[dict]:
    ep = shots["episode"]
    aspect = "9:16" if project.type == "shorts" else "16:9"
    jobs = []
    if stage == "storyboard":
        for f in shots["frames"]:
            # refs в shots.json — относительно папки проекта; CLI резолвит
            # пути от CWD, поэтому передаём абсолютные/CWD-совместимые пути.
            resolved_refs = [str(project_dir / ref) for ref in f.get("refs", [])]
            jobs.append({
                "item_id": f"{ep}/storyboard/{f['n']:03d}",
                "kind": "frame",
                "model": project.models["image"],
                "dest": episode_dir / "storyboard" / f"{f['n']:03d}.png",
                "params": {"prompt": f["prompt"], "refs": resolved_refs,
                           "aspect_ratio": aspect},
            })
    elif stage == "segments":
        for s in shots["segments"]:
            jobs.append({
                "item_id": f"{ep}/segments/{s['n']:03d}",
                "kind": "segment",
                "model": project.models["video"],
                "dest": episode_dir / "segments" / f"{s['n']:03d}.mp4",
                "params": {
                    "prompt": s["prompt"],
                    "start_frame": str(episode_dir / "storyboard"
                                       / f"{s['start_frame']:03d}.png"),
                    "end_frame": str(episode_dir / "storyboard"
                                     / f"{s['end_frame']:03d}.png"),
                    "duration": project.segment_seconds,
                    "aspect_ratio": aspect,
                },
            })
    else:  # audio (фаза 2 §5)
        for list_name, model_key, kind, subdir in AUDIO_GROUPS:
            for e in audio_plan[list_name]:
                params = ({"prompt": e["text"], "voice": e["voice"]}
                          if kind == "voice"
                          else {"prompt": e["prompt"], "duration": e["duration"]})
                jobs.append({
                    "item_id": f"{ep}/audio/{e['id']}",
                    "kind": kind,
                    "model": project.models[model_key],
                    "dest": episode_dir / "audio" / subdir
                            / f"{e['id']}{AUDIO_EXT}",
                    "params": params,
                })
    return jobs
```

9e. В `main()`: в `ap.add_argument("--stage", ...)` заменить `choices=["storyboard", "segments"]` на `choices=["storyboard", "segments", "audio"]`.

9f. В `main()` после блока валидации segments (после `return 3`) и ПЕРЕД `jobs = build_jobs(...)` добавить:

```python
    audio_plan = None
    if args.stage == "audio":
        plan_path = episode_dir / "audio.json"
        if not plan_path.exists():
            print(f"Файл плана звука не найден: {plan_path}")
            return 1
        audio_plan = load_audio_plan(plan_path, shots)
        problems = []
        for list_name, model_key, _kind, _subdir in AUDIO_GROUPS:
            if not audio_plan[list_name]:
                continue
            model_id = project.models.get(model_key)
            if not model_id:
                problems.append(f"models.{model_key} не задан в project.json "
                                f"(нужен для {list_name})")
                continue
            card = find_card(KNOWLEDGE_DIR, model_id)
            problems.extend(validate_audio_model(card))
        if problems:
            print("МОДЕЛЬ НЕ ПРОШЛА ВАЛИДАЦИЮ — генерация не запущена:")
            for p in problems:
                print(f"  - {p}")
            return 2
```

9g. Заменить строку `jobs = build_jobs(args.stage, shots, project, episode_dir, project_dir)` на:

```python
    jobs = build_jobs(args.stage, shots, project, episode_dir, project_dir,
                      audio_plan)
```

9h. Заменить печать сметы (в стадии audio модели разные):

Старый код:
```python
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.0f} кредитов "
          f"({args.stage}, модель {todo[0]['model']}).")
```

Новый код:
```python
    models_used = ", ".join(sorted({j["model"] for j in todo}))
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.0f} кредитов "
          f"({args.stage}, модели: {models_used}).")
```

- [ ] **Step 10: Прогнать тесты generate_batch — все зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: PASS (старые + 7 новых).

- [ ] **Step 11: Полный прогон**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: все passed (117 + ~19 новых).

- [ ] **Step 12: Commit**

```bash
git add scripts/factory/audio_plan.py scripts/factory/models.py scripts/generate_batch.py tests/test_audio_plan.py tests/test_models.py tests/test_generate_batch.py
git commit -m "feat: audio.json + стадия audio в generate_batch (фаза 2 Task 3)"
```

---

### Task 4: mix_audio.py — сведение

**Files:**
- Create: `scripts/mix_audio.py`
- Test: `tests/test_mix_audio.py`

Тайминг события: t = Σ фактических длительностей отрезков 1..(segment−1) + offset. Пути аудиофайлов берутся из поля `file` манифеста (не по конвенции — расширение знает только generate_batch). Ducking: `sidechaincompress` (музыка приглушается уровнем речи+SFX).

- [ ] **Step 1: Написать падающие тесты tests/test_mix_audio.py**

```python
"""Тесты mix_audio.py (спека фазы 2 §7): гейт, таймлайн, ducking, пустой план."""
import json
from pathlib import Path

import pytest

import mix_audio
from factory.ffmpeg_tools import probe_duration
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path, monkeypatch, make_clip, make_tone):
    """Проект: 2 отрезка по 2с (реальные mp4), 1 реплика + 1 музыка + 1 SFX
    (реальные aac), все аудио-items в done."""
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": "nano_banana_flash", "video": "kling3_0"},
    }), encoding="utf-8")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                   {"n": 3, "prompt": "c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    for n in (1, 2):
        make_clip(ep / "segments" / f"{n:03d}.mp4", 2.0)
    (ep / "audio.json").write_text(json.dumps({
        "voice_lines": [{"id": "vl-01", "speaker": "cat", "voice": "A",
                         "text": "Hi!", "segment": 1, "offset": 0.2}],
        "music_cues": [{"id": "mus-01", "prompt": "calm", "duration": 3,
                        "segment": 1, "offset": 0}],
        "sfx": [{"id": "sfx-01", "prompt": "creak", "duration": 1,
                 "segment": 2, "offset": 0.5}],
    }), encoding="utf-8")
    files = {
        "vl-01": make_tone(ep / "audio" / "voice" / "vl-01.m4a", 0.5),
        "mus-01": make_tone(ep / "audio" / "music" / "mus-01.m4a", 3.0),
        "sfx-01": make_tone(ep / "audio" / "sfx" / "sfx-01.m4a", 1.0),
    }
    m = Manifest(pdir / "manifest.json")
    kinds = {"vl-01": "voice", "mus-01": "music", "sfx-01": "sfx"}
    for eid, f in files.items():
        item_id = f"ep01/audio/{eid}"
        m.add(item_id, kind=kinds[eid])
        m.set_status(item_id, "generating")
        m.set_status(item_id, "generated", file=str(f))
        m.set_status(item_id, "done")
    m.save()
    monkeypatch.chdir(tmp_path)
    return pdir


def run(proj):
    return mix_audio.main(["--project", str(proj), "--episode", "ep01"])


def mix_path(proj):
    return proj / "episodes" / "ep01" / "audio" / "mix.m4a"


def test_happy_path(proj, capsys):
    assert run(proj) == 0
    assert mix_path(proj).exists()
    # Общая длительность = сумме отрезков (4с): atrim+apad
    assert abs(probe_duration(mix_path(proj)) - 4.0) < 0.3
    assert "Сведено" in capsys.readouterr().out


# done терминален — перевести готовый item обратно нельзя, поэтому гейт-тест
# строит манифест с нуля и доводит item только до generated:
def test_gate_blocks_unreviewed(proj, capsys):
    m = Manifest(proj / "manifest.json")
    f = m.get("ep01/audio/vl-01")["file"]
    m.data = {"items": {}}
    m.add("ep01/audio/vl-01", kind="voice")
    m.set_status("ep01/audio/vl-01", "generating")
    m.set_status("ep01/audio/vl-01", "generated", file=f)
    m.save()
    assert run(proj) == 3
    out = capsys.readouterr().out
    assert "заблокировано" in out
    assert "ep01/audio/vl-01" in out
    assert not mix_path(proj).exists()


def test_gate_blocks_never_generated(proj, capsys):
    (proj / "manifest.json").unlink()
    assert run(proj) == 3
    assert "не генерировался" in capsys.readouterr().out


def test_missing_audio_json_is_ok(proj, capsys):
    (proj / "episodes" / "ep01" / "audio.json").unlink()
    assert run(proj) == 0
    assert not mix_path(proj).exists()
    assert "без звука" in capsys.readouterr().out


def test_empty_plan_is_ok(proj, capsys):
    (proj / "episodes" / "ep01" / "audio.json").write_text(
        json.dumps({"voice_lines": [], "music_cues": [], "sfx": []}),
        encoding="utf-8")
    assert run(proj) == 0
    assert not mix_path(proj).exists()
    assert "пуст" in capsys.readouterr().out


def test_overflow_warning(proj, capsys):
    # Реплика 0.5с на offset 1.8 при отрезке 2с → вылезает за границу
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"][0]["offset"] = 1.8
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert "вылезает" in capsys.readouterr().out


def test_voice_only_no_music(proj):
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["music_cues"] = []
    data["sfx"] = []
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert mix_path(proj).exists()


def test_music_only_no_speech(proj):
    ep = proj / "episodes" / "ep01"
    data = json.loads((ep / "audio.json").read_text(encoding="utf-8"))
    data["voice_lines"] = []
    data["sfx"] = []
    (ep / "audio.json").write_text(json.dumps(data), encoding="utf-8")
    assert run(proj) == 0
    assert mix_path(proj).exists()


def test_missing_audio_file(proj, capsys):
    (proj / "episodes" / "ep01" / "audio" / "voice" / "vl-01.m4a").unlink()
    assert run(proj) == 1
    assert "не найден" in capsys.readouterr().out
```

- [ ] **Step 2: Запустить — убедиться, что падают на импорте**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mix_audio.py -q`
Expected: ERROR — `No module named 'mix_audio'`.

- [ ] **Step 3: Написать scripts/mix_audio.py**

```python
"""Сведение аудиодорожки эпизода (спека фазы 2 §7, основная §11).

Запускать из корня репозитория:
  python scripts/mix_audio.py --project projects/pilot --episode ep01

Тайминг: segment+offset из audio.json; абсолютные таймкоды вычисляются по
фактическим длительностям файлов отрезков (ffprobe). Музыка приглушается
под репликами/SFX (sidechaincompress). Громкости — константы ниже.
Пути аудиофайлов — из поля file манифеста.

Коды выхода: 0 успех (или нет/пустой audio.json — без файла);
1 ошибка данных/ffmpeg; 3 аудио не принято ревью.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.audio_plan import is_empty, load_audio_plan
from factory.ffmpeg_tools import FfmpegError, probe_duration, run_ffmpeg
from factory.manifest import Manifest, ManifestError
from factory.shots import load_shots

ACCEPTED = {"done", "accepted_with_notes"}
VOICE_VOLUME = 1.0
SFX_VOLUME = 0.7
MUSIC_VOLUME = 0.35
# Приглушение музыки под репликами/SFX; параметры уточнить на smoke (Task 6)
DUCK = "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=300"


def segment_timeline(shots: dict, episode_dir: Path):
    """(старт, длительность) каждого отрезка по фактическим файлам + общая длина."""
    starts: dict[int, float] = {}
    durs: dict[int, float] = {}
    t = 0.0
    for s in sorted(shots["segments"], key=lambda s: s["n"]):
        f = episode_dir / "segments" / f"{s['n']:03d}.mp4"
        if not f.exists():
            raise FfmpegError(f"Файл отрезка не найден: {f}")
        d = probe_duration(f)
        starts[s["n"]] = t
        durs[s["n"]] = d
        t += d
    return starts, durs, t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")
    ep = shots["episode"]

    plan_path = episode_dir / "audio.json"
    if not plan_path.exists():
        print(f"audio.json не найден ({plan_path}) — сведение не требуется, "
              "сборка пойдёт без звука.")
        return 0
    plan = load_audio_plan(plan_path, shots)
    if is_empty(plan):
        print("audio.json пуст — сведение не требуется, "
              "сборка пойдёт без звука.")
        return 0

    # Гейт: все аудио-единицы приняты ревью (симметрично гейтам кадров/отрезков)
    problems = {}
    for entry in plan["voice_lines"] + plan["music_cues"] + plan["sfx"]:
        item_id = f"{ep}/audio/{entry['id']}"
        try:
            status = manifest.get(item_id)["status"]
        except ManifestError:
            problems[item_id] = "не генерировался"
            continue
        if status not in ACCEPTED:
            problems[item_id] = f"статус {status}"
    if problems:
        print("АУДИО НЕ ПРИНЯТО РЕВЬЮ — сведение заблокировано:")
        for item_id in sorted(problems):
            print(f"  - {item_id}: {problems[item_id]}")
        return 3

    try:
        starts, seg_durs, total = segment_timeline(shots, episode_dir)

        def collect(list_name: str, volume: float):
            events = []
            for e in plan[list_name]:
                item_id = f"{ep}/audio/{e['id']}"
                path = Path(manifest.get(item_id)["file"])
                if not path.exists():
                    raise FfmpegError(
                        f"Аудиофайл из манифеста не найден: {path}")
                t = starts[e["segment"]] + e["offset"]
                dur = probe_duration(path)
                if e["offset"] + dur > seg_durs[e["segment"]] + 0.01:
                    print(f"ВНИМАНИЕ: {e['id']} ({dur:.2f}с) вылезает за "
                          f"границу отрезка {e['segment']} "
                          f"({seg_durs[e['segment']]:.2f}с).")
                events.append((path, t, volume))
            return events

        speech = collect("voice_lines", VOICE_VOLUME) + collect("sfx", SFX_VOLUME)
        music = collect("music_cues", MUSIC_VOLUME)
    except FfmpegError as e:
        print(f"ОШИБКА: {e}")
        return 1

    inputs: list[str] = []
    filters: list[str] = []
    labels_speech: list[str] = []
    labels_music: list[str] = []
    for idx, (path, t, vol) in enumerate(speech + music):
        inputs.extend(["-i", str(path)])
        label = f"a{idx}"
        filters.append(f"[{idx}:a]volume={vol},"
                       f"adelay={int(round(t * 1000))}:all=1[{label}]")
        (labels_speech if idx < len(speech) else labels_music).append(label)

    def add_amix(labels: list[str], out: str) -> None:
        if len(labels) == 1:
            filters.append(f"[{labels[0]}]anull[{out}]")
        else:
            filters.append(
                "".join(f"[{lb}]" for lb in labels)
                + f"amix=inputs={len(labels)}:duration=longest:normalize=0"
                + f"[{out}]")

    if speech and music:
        add_amix(labels_speech, "speech")
        add_amix(labels_music, "music")
        filters.append("[speech]asplit=2[sp1][sp2]")
        filters.append(f"[music][sp1]{DUCK}[duck]")
        filters.append("[duck][sp2]amix=inputs=2:duration=longest:"
                       "normalize=0[premix]")
    elif speech:
        add_amix(labels_speech, "premix")
    else:
        add_amix(labels_music, "premix")
    filters.append(f"[premix]atrim=0:{total:.3f},"
                   f"apad=whole_dur={total:.3f}[mix]")

    dest = episode_dir / "audio" / "mix.m4a"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name("mix.tmp.m4a")
    try:
        run_ffmpeg(inputs + ["-filter_complex", ";".join(filters),
                             "-map", "[mix]", "-c:a", "aac", str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1

    print(f"Сведено: {dest} ({probe_duration(dest):.2f}с, "
          f"реплик+SFX: {len(speech)}, музыки: {len(music)}).")
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [ ] **Step 4: Прогнать тесты — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_mix_audio.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Полный прогон**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: все passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/mix_audio.py tests/test_mix_audio.py
git commit -m "feat: mix_audio.py — сведение дорожки с ducking и гейтом ревью (фаза 2 Task 4)"
```

---

### Task 5: интеграция звука в assemble.py

**Files:**
- Modify: `scripts/assemble.py`
- Test: `tests/test_assemble.py` (добавить тесты в конец)

- [ ] **Step 1: Написать падающие тесты (в конец tests/test_assemble.py)**

```python
# ---- Task 5: наложение звука ----

def test_audio_overlay_when_mix_exists(proj, make_tone, capsys):
    make_tone(proj / "episodes" / "ep01" / "audio" / "mix.m4a", 10.0)
    assert run(proj) == 0
    dest = proj / "episodes" / "ep01" / "final" / "ep01.mp4"
    assert has_audio_stream(dest)
    assert "со звуком" in capsys.readouterr().out


def test_no_audio_when_mix_missing(proj, capsys):
    assert run(proj) == 0
    dest = proj / "episodes" / "ep01" / "final" / "ep01.mp4"
    assert not has_audio_stream(dest)
    assert "без звука" in capsys.readouterr().out
```

- [ ] **Step 2: Запустить — первый тест падает**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_assemble.py -q`
Expected: `test_audio_overlay_when_mix_exists` FAIL (нет аудиопотока), остальные PASS. Также упадёт `test_happy_path` НЕ должен — он без mix.m4a.

- [ ] **Step 3: Изменить assemble.py — блок склейки**

Старый код (от `inputs: list[str] = []` до `return 1` включительно в except):

```python
    inputs: list[str] = []
    for f in files:
        inputs.extend(["-i", str(f)])
    n = len(files)
    filt = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    try:
        run_ffmpeg(inputs + ["-filter_complex", filt, "-map", "[v]",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1
```

Новый код:

```python
    inputs: list[str] = []
    for f in files:
        inputs.extend(["-i", str(f)])
    n = len(files)
    filt = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    maps = ["-map", "[v]"]
    mix = episode_dir / "audio" / "mix.m4a"
    audio_note = "без звука (audio/mix.m4a не найден)"
    if mix.exists():
        inputs.extend(["-i", str(mix)])
        maps.extend(["-map", f"{n}:a", "-c:a", "aac", "-shortest"])
        audio_note = "со звуком"
    try:
        run_ffmpeg(inputs + ["-filter_complex", filt] + maps +
                   ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp)])
        os.replace(tmp, dest)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        print(f"ОШИБКА ffmpeg: {e}")
        return 1
```

И заменить финальную печать:

Старый код:
```python
    print(f"Собрано: {dest} ({fact:.2f}с, {n} отрезков, без звука).")
```

Новый код:
```python
    print(f"Собрано: {dest} ({fact:.2f}с, {n} отрезков, {audio_note}).")
```

Также обновить докстринг модуля: заменить строку `Гейт: все отрезки эпизода...` абзацем:

```
Гейт: все отрезки эпизода приняты ревью (done/accepted_with_notes), иначе
список + exit 3. Если существует audio/mix.m4a (scripts/mix_audio.py) —
дорожка накладывается; иначе сборка идёт без звука (позволяет собрать
видео до готовности звука).
```

- [ ] **Step 4: Прогнать тесты — все зелёные** (в т.ч. `test_happy_path` с «без звука»)

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_assemble.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Полный прогон**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: все passed.

- [ ] **Step 6: Обновить CLAUDE.md** — в раздел «Структура» после строки про review.py добавить:

```
- scripts/mix_audio.py — сведение аудиодорожки эпизода (тайминг по audio.json)
- scripts/assemble.py — сборка финального mp4 из отрезков (+звук, если сведён)
```

- [ ] **Step 7: Commit**

```bash
git add scripts/assemble.py tests/test_assemble.py CLAUDE.md
git commit -m "feat: наложение звука в assemble.py (фаза 2 Task 5)"
```

---

### Task 6: финальный боевой smoke на _smoke

**⚠ Выполняется в ОСНОВНОЙ сессии с пользователем (тратит ~5–10 кр, каждый запуск со сметой — подтверждение).**

Состояние `projects/_smoke` после фазы 1: 2 кадра + 1 отрезок kling3_0 (5 с), все в `done`. Манифест содержит item'ы `ep01/storyboard/001..002`, `ep01/segments/001`.

- [ ] **Step 1: Написать `projects/_smoke/episodes/ep01/audio.json`**

Голос и duration — из карточек Task 2 (вместо `<voice>` — проверенный спайком голос; duration музыки/SFX — допустимые по карточкам значения, ориентир ниже):

```json
{
  "voice_lines": [
    {"id": "vl-01", "speaker": "cat", "voice": "<voice>",
     "text": "Engaging thrusters. Next stop: the cheese nebula!",
     "segment": 1, "offset": 0.3}
  ],
  "music_cues": [
    {"id": "mus-01", "prompt": "playful orchestral space adventure, cartoon style",
     "duration": 5, "segment": 1, "offset": 0}
  ],
  "sfx": [
    {"id": "sfx-01", "prompt": "rocket thruster whoosh",
     "duration": 2, "segment": 1, "offset": 0.0}
  ]
}
```

- [ ] **Step 2: Генерация звука (смета → подтверждение пользователя)**

Run: `python scripts/generate_batch.py --project projects/_smoke --episode ep01 --stage audio`
Expected: смета ~5 кр (2 + 1.88 + 1.25), после «y» — 3 файла в `projects/_smoke/episodes/ep01/audio/{voice,music,sfx}/`, статусы `generated`.

- [ ] **Step 3: Ревью звука**

Run: `python scripts/review.py --project projects/_smoke list --status generated` → прослушать 3 файла с пользователем → `python scripts/review.py --project projects/_smoke accept ep01/audio/vl-01 ep01/audio/mus-01 ep01/audio/sfx-01`.

- [ ] **Step 4: Сведение и сборка**

Run: `python scripts/mix_audio.py --project projects/_smoke --episode ep01`
Expected: `mix.m4a` ~5 с, без предупреждений (или обоснованные).
Run: `python scripts/assemble.py --project projects/_smoke --episode ep01`
Expected: `projects/_smoke/episodes/ep01/final/ep01.mp4` «со звуком»; контроль ±5% молчит. Посмотреть/послушать файл с пользователем; при плохом балансе громкостей — поправить константы VOICE_VOLUME/SFX_VOLUME/MUSIC_VOLUME/DUCK в mix_audio.py и пересвести (бесплатно).

- [ ] **Step 5: Проверка resume**

Run: `python scripts/generate_batch.py --project projects/_smoke --episode ep01 --stage audio` повторно.
Expected: «Всё уже сгенерировано — нечего делать.», ноль трат. mix/assemble повторно — идемпотентно перезаписывают результат.

- [ ] **Step 6: Зафиксировать результаты**

Создать `docs/superpowers/plans/2026-06-12-phase2-progress.md` (handoff: статус задач, фактические списания smoke, наблюдения по качеству звука/ducking, открытые вопросы). Обновить карточки аудио-моделей наблюдениями smoke, если есть новые.

- [ ] **Step 7: Финальный прогон и commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: все passed.

```bash
git add projects/_smoke docs/superpowers/plans/2026-06-12-phase2-progress.md knowledge/audio
git commit -m "docs: боевой smoke фазы 2 пройден — звук+сведение+сборка (Task 6)"
```

- [ ] **Step 8: Завершение ветки** — superpowers:finishing-a-development-branch с пользователем (merge в master / дальнейшая судьба).
