# Контент-завод — Фаза 1: конвейер генерации. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Работающий конвейер генерации: по `shots.json` завод считает смету, батчем генерирует кадры (nano banana 2) и видеоотрезки (Kling 2.0, start/end кадры) через Higgsfield CLI, ведёт манифест и умеет возобновляться после сбоя.

**Architecture:** Python-пакет `scripts/factory/` (project, manifest, models, shots, higgsfield_client) + entry-скрипт `scripts/generate_batch.py`. Все best practices и матрицы возможностей моделей — в `knowledge/`-карточках с YAML-frontmatter. Тесты — pytest, внешний CLI мокается.

**Tech Stack:** Python 3.11+, pytest, PyYAML, Higgsfield CLI (`@higgsfield/cli` через npm), git. ОС — Windows (PowerShell).

**Контекст:** спека — `docs/superpowers/specs/2026-06-11-content-factory-design.md`. Это фаза 1 из 3 (фаза 2 — звук и сборка; фаза 3 — скиллы-этапы, CLAUDE.md-конституция, пилот).

---

## Файловая структура фазы 1

| Путь | Ответственность |
|---|---|
| `CLAUDE.md` | Ориентация по репозиторию для разработчика (полная «конституция завода» — фаза 3) |
| `requirements.txt`, `pytest.ini`, `.gitignore` | Окружение |
| `knowledge/higgsfield-cli.md` | Контракт CLI: точные команды, форматы JSON, грабли (результат спайка) |
| `knowledge/_template.md` | Шаблон карточки модели |
| `knowledge/images/*.md`, `knowledge/video/*.md` | Карточки моделей: матрица возможностей + best practices |
| `scripts/factory/project.py` | Загрузка и валидация `project.json` |
| `scripts/factory/manifest.py` | Манифест: статусы, переходы, идемпотентность |
| `scripts/factory/models.py` | Чтение карточек, валидация возможностей модели |
| `scripts/factory/shots.py` | Загрузка и валидация `shots.json` (цепочка кадров) |
| `scripts/factory/higgsfield_client.py` | Адаптер Higgsfield CLI (estimate/submit/wait/download) |
| `scripts/generate_batch.py` | Оркестратор: смета → подтверждение → батч → манифест |
| `tests/test_*.py` | Тесты всех модулей |

---

### Task 1: Каркас репозитория и окружение

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.gitignore`, `CLAUDE.md`, `scripts/factory/__init__.py`, `knowledge/.gitkeep`, `projects/.gitkeep`, `tests/.gitkeep`

- [ ] **Step 1: Создать файлы окружения**

`requirements.txt`:
```
pytest>=8.0
pyyaml>=6.0
```

`pytest.ini`:
```ini
[pytest]
pythonpath = scripts
testpaths = tests
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
projects/**/*.png
projects/**/*.mp4
projects/**/*.mp3
projects/**/*.wav
spike/
```

`CLAUDE.md`:
```markdown
# content-factory

ИИ-конвейер создания видео: от брифа до готовой серии со звуком.
Спека: docs/superpowers/specs/2026-06-11-content-factory-design.md

## Структура
- scripts/factory/ — Python-пакет (project, manifest, models, shots, higgsfield_client)
- scripts/generate_batch.py — батч-генерация кадров/отрезков
- knowledge/ — карточки моделей (матрица возможностей + best practices) и контракт CLI
- projects/ — контент-проекты (project.json, manifest.json, bible/, episodes/)
- tests/ — pytest

## Правила
- Скрипты запускаются ИЗ КОРНЯ репозитория (пути knowledge/ и projects/ — относительные).
- Тесты: `pytest -q`. Перед коммитом тесты должны быть зелёными.
- Точные флаги Higgsfield CLI живут ТОЛЬКО в knowledge/higgsfield-cli.md
  и scripts/factory/higgsfield_client.py — больше нигде.
- Полная «конституция завода» (этапы, чекпоинты, скиллы) появится в фазе 3.
```

Пустые файлы: `scripts/factory/__init__.py`, `knowledge/.gitkeep`, `projects/.gitkeep`, `tests/.gitkeep`.

- [ ] **Step 2: Создать venv и поставить зависимости**

```powershell
cd C:\Users\lar\content-factory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
```
Ожидаем: `no tests ran` (выход без ошибок конфигурации).

- [ ] **Step 3: Проверить внешние инструменты**

```powershell
ffmpeg -version        # нужен для фазы 2, проверяем сразу; нет — winget install ffmpeg
node --version         # нужен npm
npm install -g @higgsfield/cli
higgsfield --help
higgsfield auth login  # откроет браузер, авторизация через аккаунт Higgsfield
```
Ожидаем: `higgsfield --help` печатает список команд; после login — успешная авторизация. Если имя бинаря иное (например `hf`) — зафиксировать фактическое и использовать его далее везде.

- [ ] **Step 4: Commit**

```powershell
git add -A; git commit -m "chore: scaffold repo (env, pytest, gitignore, CLAUDE.md)"
```

---

### Task 2: Спайк Higgsfield CLI (риск-киллер)

Цель: подтвердить сквозной путь «промпт → картинка → два кадра → видео по start/end → файлы на диске» и зафиксировать точный контракт CLI. **Без этого знания нельзя писать `higgsfield_client.py`.**

**Files:**
- Create: `knowledge/higgsfield-cli.md`
- Рабочая папка экспериментов: `spike/` (в .gitignore)

- [ ] **Step 1: Изучить команды и каталог моделей**

```powershell
higgsfield --help
higgsfield model list          # или ближайший аналог из --help
```
Записать: точные id моделей nano banana 2, nano banana pro, Kling 2.0, Seedance 2.0 (как их называет CLI).

- [ ] **Step 2: Смета и генерация одной картинки**

Найти в `--help` команду расчёта стоимости и генерации; ожидаемый по докам шаблон:
```powershell
higgsfield generate cost  --model <nano-banana-2-id> ... # смета в кредитах
higgsfield generate create --model <nano-banana-2-id> --prompt "flat 2D cartoon, orange cat astronaut standing in a spaceship corridor, full body, simple shapes, bold outlines" --aspect-ratio 16:9
higgsfield generate get <job_id>        # статус
higgsfield generate download <job_id> --output spike/cat1.png   # или скачать по URL из get
```
Ожидаем: `spike/cat1.png` существует и открывается. Записать фактические команды/флаги/JSON-ответы.

- [ ] **Step 3: Второй кадр того же персонажа (проверка референсов)**

Сгенерировать второй кадр: тот же кот, другая поза («reaching toward a control panel»), передав `spike/cat1.png` как референс-изображение (найти флаг загрузки/референса: `higgsfield upload` + параметр референса). Ожидаем: `spike/cat2.png`, персонаж визуально тот же. Записать механику референсов.

- [ ] **Step 4: Видео Kling 2.0 по start/end кадрам — ключевая проверка**

```powershell
# шаблон; точные флаги взять из --help
higgsfield generate create --model <kling-2.0-id> --start-frame spike/cat1.png --end-frame spike/cat2.png --prompt "the cat slowly reaches toward the control panel, subtle camera push-in" --duration 5
higgsfield generate download <job_id> --output spike/seg1.mp4
```
Ожидаем: `spike/seg1.mp4` — 5-секундный отрезок, начинающийся кадром 1 и заканчивающийся кадром 2.

**Если Kling 2.0 через CLI не принимает end-кадр:** проверить по очереди Kling 2.1 / 2.5 Turbo / 2.6 / 3.0 и Seedance 2.0; зафиксировать, какие версии поддерживают start+end. Если НИ ОДНА доступная модель не поддерживает — СТОП, вернуться к пользователю: схема склейки из спеки требует пересмотра.

- [ ] **Step 5: Записать контракт в knowledge/higgsfield-cli.md**

Структура файла (заполнить фактами из шагов 1–4):
```markdown
# Higgsfield CLI — контракт (спайк YYYY-MM-DD)

## Версия CLI и аутентификация
## Каталог моделей (фактические id)
## Команды: смета / создание / статус / скачивание (точный синтаксис)
## Жизненный цикл задачи (статусы, типичное время ожидания)
## Формат JSON-ответов (примеры)
## Референс-изображения и загрузка файлов
## Start/end кадры: какие видеомодели поддерживают (проверено)
## Стоимости, замеченные в спайке (кредиты за картинку/5с видео)
## Грабли
```

- [ ] **Step 6: Commit**

```powershell
git add knowledge/higgsfield-cli.md; git commit -m "docs: higgsfield CLI contract from day-1 spike"
```

---

### Task 3: factory/project.py — загрузка и валидация project.json

**Files:**
- Create: `scripts/factory/project.py`
- Test: `tests/test_project.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_project.py`:
```python
import json
import pytest
from factory.project import load_project, ProjectError


def write(tmp_path, data):
    p = tmp_path / "project.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


BASE = {
    "name": "pilot", "type": "animated_series", "theme": "space cats",
    "audience": "6-9", "episodes": 1, "episode_duration_sec": 75,
    "models": {"image": "nano-banana-2", "video": "kling-2.0"},
}


def test_loads_valid_animated_series(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.type == "animated_series"
    assert p.segment_seconds == 5            # high quality — дефолт
    assert p.review_strictness == "medium"   # дефолт


def test_budget_mode_gives_10s_segments(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "quality_mode": "budget"}))
    assert p.segment_seconds == 10


def test_missing_required_field_raises(tmp_path):
    data = {k: v for k, v in BASE.items() if k != "audience"}
    with pytest.raises(ProjectError, match="audience"):
        load_project(write(tmp_path, data))


def test_unknown_type_raises(tmp_path):
    with pytest.raises(ProjectError, match="unknown project type"):
        load_project(write(tmp_path, {**BASE, "type": "opera"}))


def test_missing_video_model_raises(tmp_path):
    with pytest.raises(ProjectError, match="models.video"):
        load_project(write(tmp_path, {**BASE, "models": {"image": "nano-banana-2"}}))
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_project.py -q`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'factory.project'`

- [ ] **Step 3: Реализация**

`scripts/factory/project.py`:
```python
"""Загрузка и валидация project.json (бриф проекта, спека §4)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

VALID_QUALITY = {"high": 5, "budget": 10}  # режим -> секунд на отрезок (спека §4)
VALID_STRICTNESS = {"low", "medium", "high"}

# Обязательные поля по типам контента (ТЗ п.1.1–1.5)
REQUIRED_BY_TYPE = {
    "film": ["duration_sec", "theme"],
    "series": ["theme", "episodes", "episode_duration_sec"],
    "animated_film": ["duration_sec", "theme", "audience"],
    "animated_series": ["theme", "audience", "episodes", "episode_duration_sec"],
    "shorts": ["duration_sec", "theme"],
}


class ProjectError(ValueError):
    pass


@dataclass
class Project:
    name: str
    type: str
    theme: str
    language: str
    models: dict
    quality_mode: str
    review_strictness: str
    raw: dict

    @property
    def segment_seconds(self) -> int:
        return VALID_QUALITY[self.quality_mode]


def load_project(path: Path) -> Project:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    ptype = data.get("type")
    if ptype not in REQUIRED_BY_TYPE:
        raise ProjectError(f"unknown project type: {ptype!r}")

    missing = [f for f in REQUIRED_BY_TYPE[ptype] if f not in data]
    if missing:
        raise ProjectError(f"missing required fields for {ptype}: {missing}")

    for m in ("image", "video"):
        if m not in data.get("models", {}):
            raise ProjectError(f"models.{m} is required")

    quality = data.get("quality_mode", "high")
    if quality not in VALID_QUALITY:
        raise ProjectError(f"unknown quality_mode: {quality!r}")

    strictness = data.get("review_strictness", "medium")
    if strictness not in VALID_STRICTNESS:
        raise ProjectError(f"unknown review_strictness: {strictness!r}")

    return Project(
        name=data["name"], type=ptype, theme=data["theme"],
        language=data.get("language", "en"), models=data["models"],
        quality_mode=quality, review_strictness=strictness, raw=data,
    )
```

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_project.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```powershell
git add scripts/factory/project.py tests/test_project.py
git commit -m "feat: project.json loading and validation"
```

---

### Task 4: factory/manifest.py — память завода

**Files:**
- Create: `scripts/factory/manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_manifest.py`:
```python
import pytest
from factory.manifest import Manifest, ManifestError


def test_add_is_idempotent(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.add("ep01/storyboard/001", kind="frame")  # повторное add не сбрасывает статус
    assert m.get("ep01/storyboard/001")["status"] == "generating"


def test_done_is_terminal(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    m.set_status("x", "done", file="x.png")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")


def test_rejected_requires_reason(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="reject_reason"):
        m.set_status("x", "rejected")
    m.set_status("x", "rejected", reject_reason="anatomy: extra fingers")
    m.set_status("x", "pending")  # перегенерация разрешена


def test_pending_filter_and_persistence(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest(path)
    m.add("a", kind="frame")
    m.add("b", kind="segment")
    m.set_status("a", "generating")
    m.set_status("a", "done", file="a.png", credits_spent=2.0)
    m.save()

    m2 = Manifest(path)  # перечитываем с диска
    assert m2.pending() == ["b"]
    assert m2.pending(kind="frame") == []
    assert m2.credits_total() == 2.0
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.manifest'`

- [ ] **Step 3: Реализация**

`scripts/factory/manifest.py`:
```python
"""Манифест проекта — память завода (спека §10).

Статусы: pending -> generating -> done | rejected | accepted_with_notes.
rejected/accepted_with_notes -> pending = перегенерация.
generating -> pending = возврат в очередь после технического сбоя.
"""
from __future__ import annotations

import json
from pathlib import Path

STATUSES = {"pending", "generating", "done", "rejected", "accepted_with_notes"}
ALLOWED = {
    "pending": {"generating"},
    "generating": {"done", "rejected", "accepted_with_notes", "pending"},
    "rejected": {"pending"},
    "accepted_with_notes": {"pending"},
    "done": set(),
}


class ManifestError(ValueError):
    pass


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"items": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, item_id: str, kind: str) -> None:
        self.data["items"].setdefault(item_id, {
            "kind": kind, "status": "pending", "attempts": 0,
            "credits_spent": 0.0, "file": None, "job_id": None,
            "reject_reason": None, "notes": None,
        })

    def get(self, item_id: str) -> dict:
        return self.data["items"][item_id]

    def set_status(self, item_id: str, status: str, **fields) -> None:
        if status not in STATUSES:
            raise ManifestError(f"unknown status: {status!r}")
        item = self.get(item_id)
        if status not in ALLOWED[item["status"]]:
            raise ManifestError(
                f"{item_id}: {item['status']} -> {status} is not allowed")
        if status == "rejected" and not fields.get("reject_reason"):
            raise ManifestError(f"{item_id}: rejected requires reject_reason")
        item.update(status=status, **fields)

    def pending(self, kind: str | None = None) -> list[str]:
        return [i for i, it in self.data["items"].items()
                if it["status"] == "pending"
                and (kind is None or it["kind"] == kind)]

    def credits_total(self) -> float:
        return sum(it["credits_spent"] for it in self.data["items"].values())
```

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_manifest.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```powershell
git add scripts/factory/manifest.py tests/test_manifest.py
git commit -m "feat: project manifest with status transitions and resume support"
```

---

### Task 5: Карточки моделей

**Files:**
- Create: `knowledge/_template.md`
- Create: `knowledge/images/nano-banana-2.md`, `knowledge/images/nano-banana-pro.md`
- Create: `knowledge/video/kling-2.0.md`, `knowledge/video/seedance-2.0.md`
- Create: скелеты — `knowledge/video/kling-2.1.md`, `kling-2.5-turbo.md`, `kling-2.6.md`, `kling-3.0.md`, `veo-3.md`, `veo-3.1.md`, `grok-video.md`; `knowledge/images/soul-2.0.md`, `seedream-4.0.md`, `grok-image.md`

- [ ] **Step 1: Шаблон карточки**

`knowledge/_template.md`:
```markdown
---
id: <model-id>           # точный id из higgsfield model list
type: image | video
family: <nano-banana|kling|seedance|veo|grok|soul|seedream>
status: skeleton         # skeleton | verified (после проверки спайком/использованием)
supports_start_end_frame: false   # для video: подтверждать только экспериментом
native_audio: false
max_clip_seconds: 0      # для video
aspect_ratios: []
cost_tier: unknown       # low | medium | high
---

# <Название модели>

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
```

- [ ] **Step 2: Базовые карточки (полные)**

В frontmatter всех четырёх базовых карточек подставить **фактические id и значения из `knowledge/higgsfield-cli.md`** (Task 2). `status: verified` ставить только полям, проверенным спайком.

`knowledge/images/nano-banana-2.md`:
```markdown
---
id: nano-banana-2        # сверить с higgsfield model list
type: image
family: nano-banana
status: verified
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: ["16:9", "9:16", "1:1"]
cost_tier: low
---

# Nano Banana 2 — рабочая лошадка раскадровки

## Сильные стороны
Быстрая и дешёвая генерация кадров; хорошо держит персонажа по референс-изображению;
уверенная стилизация под flat/cartoon 2D.

## Структура промпта
`[канонический блок персонажа — ДОСЛОВНО из bible/characters/*.md] +
[действие в кадре] + [окружение] + [канонический блок стиля из style-guide.md] +
[композиция/камера: wide shot / close-up / over-the-shoulder]`.
Референсы персонажей передавать изображениями в каждый кадр с персонажем.
Описывать желаемое, а не запрещённое (негативные формулировки работают плохо).

## Best practices для start/end пар
End-кадр отрезка генерировать с тем же описанием окружения и стиля, что и start-кадр,
меняя только позу/действие — иначе видеомодель получит несостыкуемые кадры.

## Типовые ошибки
Мелкий текст на объектах (вывески, экраны) — артефактится: текст отдавать
nano banana pro. Руки в сложных позах — проверять на ревью в первую очередь.
```

`knowledge/images/nano-banana-pro.md`:
```markdown
---
id: nano-banana-pro      # сверить с higgsfield model list
type: image
family: nano-banana
status: verified
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: ["16:9", "9:16", "1:1"]
cost_tier: medium
---

# Nano Banana Pro — персонажи, текст, 4K

## Когда использовать
Character sheets (этап 5), кадры с читаемым текстом (вывески, баннеры шортсов),
ключевые кадры, где нужна максимальная детализация. Дороже nano banana 2 —
для массовой раскадровки не использовать.

## Структура промпта
Как у nano banana 2. Для character sheet: «character sheet, front view / side view /
back view / three-quarter view, neutral pose, plain background» + канонический блок
персонажа + блок стиля.

## Типовые ошибки
Перегруз промпта деталями ломает композицию листа — один персонаж, один лист.
```

`knowledge/video/kling-2.0.md`:
```markdown
---
id: kling-2.0            # сверить с higgsfield model list
type: video
family: kling
status: verified         # ставится по результату спайка (Task 2, Step 4)
supports_start_end_frame: true   # ПОДТВЕРДИТЬ спайком; если нет — см. higgsfield-cli.md
native_audio: false
max_clip_seconds: 10
aspect_ratios: ["16:9", "9:16", "1:1"]
cost_tier: low
---

# Kling 2.0 — базовая видеомодель (budget)

## Когда использовать
Дефолт budget-режима (спека §2): дешёвые отрезки 5/10 секунд по start/end кадрам.

## Структура промпта движения
Кадры уже задают композицию — промпт описывает ТОЛЬКО движение:
`[что движется и как] + [движение камеры: static / slow push-in / pan left] + [темп]`.
Не переописывать сцену и персонажа — модель интерполирует между кадрами.

## Типовые ошибки
Резкая смена композиции между start и end кадрами → рваная интерполяция
(правило для этапа раскадровки, см. карточку nano banana 2).
Слишком длинный промпт → модель игнорирует кадры и «выдумывает» сцену.
```

`knowledge/video/seedance-2.0.md`:
```markdown
---
id: seedance-2.0         # сверить с higgsfield model list
type: video
family: seedance
status: verified         # ставится по результату спайка; start/end проверить отдельно
supports_start_end_frame: true   # ПОДТВЕРДИТЬ спайком
native_audio: false
max_clip_seconds: 10
aspect_ratios: ["16:9", "9:16", "1:1"]
cost_tier: high
---

# Seedance 2.0 — качественная видеомодель (high quality)

## Когда использовать
Дефолт high-quality-режима (спека §2): лучше физика движения и стабильность
персонажа, дороже Kling 2.0.

## Структура промпта движения
Как у Kling 2.0: только движение, не сцена. Выдерживает чуть более детальные
описания движения (вторичная анимация: хвост, ткань, волосы).

## Типовые ошибки
Те же, что у Kling 2.0. На статичных планах (start ≈ end) добавлять
micro-движение в промпт («subtle idle sway»), иначе возможен «стоп-кадр».
```

- [ ] **Step 3: Скелеты остальных заявленных семейств**

Скопировать `_template.md` в каждый файл из списка **Files** выше, заполнив только `id`, `type`, `family` (содержимое — скелет, это политика спеки §6: best practices наполняются по мере использования).

- [ ] **Step 4: Commit**

```powershell
git add knowledge/
git commit -m "docs: model knowledge cards (base: nano-banana-2/pro, kling-2.0, seedance-2.0; skeletons for kling/veo/grok/soul/seedream families)"
```

---

### Task 6: factory/models.py — чтение карточек и валидация возможностей

**Files:**
- Create: `scripts/factory/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_models.py`:
```python
import pytest
from factory.models import find_card, load_card, validate_video_model, ModelError

CARD = """---
id: kling-2.0
type: video
family: kling
status: verified
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 10
cost_tier: low
---
# Kling 2.0
"""


def write_card(tmp_path, text, name="kling-2.0.md"):
    d = tmp_path / "video"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_load_and_find_card(tmp_path):
    kdir = write_card(tmp_path, CARD)
    card = find_card(kdir, "kling-2.0")
    assert card["supports_start_end_frame"] is True
    assert card["max_clip_seconds"] == 10


def test_find_unknown_model_raises(tmp_path):
    kdir = write_card(tmp_path, CARD)
    with pytest.raises(ModelError, match="no knowledge card"):
        find_card(kdir, "sora-99")


def test_validate_ok_for_verified_card(tmp_path):
    card = load_card(write_card(tmp_path, CARD) / "video" / "kling-2.0.md")
    assert validate_video_model(card, segment_seconds=5) == []


def test_validate_flags_problems(tmp_path):
    bad = CARD.replace("supports_start_end_frame: true",
                       "supports_start_end_frame: false") \
              .replace("status: verified", "status: skeleton") \
              .replace("max_clip_seconds: 10", "max_clip_seconds: 4")
    card = load_card(write_card(tmp_path, bad) / "video" / "kling-2.0.md")
    problems = validate_video_model(card, segment_seconds=5)
    assert len(problems) == 3  # нет start/end, клип короче отрезка, карточка-скелет
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.models'`

- [ ] **Step 3: Реализация**

`scripts/factory/models.py`:
```python
"""Карточки моделей: YAML-frontmatter с матрицей возможностей (спека §6)."""
from __future__ import annotations

from pathlib import Path

import yaml


class ModelError(ValueError):
    pass


def load_card(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ModelError(f"{path}: card has no YAML frontmatter")
    _, fm, _body = text.split("---", 2)
    card = yaml.safe_load(fm)
    for req in ("id", "type", "status"):
        if req not in card:
            raise ModelError(f"{path}: frontmatter missing {req!r}")
    return card


def find_card(knowledge_dir: Path, model_id: str) -> dict:
    for p in sorted(Path(knowledge_dir).rglob("*.md")):
        if p.name.startswith("_"):
            continue
        card = load_card(p)
        if card["id"] == model_id:
            return card
    raise ModelError(f"no knowledge card for model {model_id!r}")


def validate_video_model(card: dict, segment_seconds: int) -> list[str]:
    """Спека §6: валидация выбора модели ДО траты кредитов."""
    problems: list[str] = []
    if card["type"] != "video":
        problems.append(f"{card['id']}: not a video model")
        return problems
    if not card.get("supports_start_end_frame"):
        problems.append(
            f"{card['id']}: no start/end frame support — "
            "segment chaining (спека §4) will break")
    if card.get("max_clip_seconds", 0) < segment_seconds:
        problems.append(
            f"{card['id']}: max clip {card.get('max_clip_seconds', 0)}s "
            f"< required {segment_seconds}s")
    if card.get("status") == "skeleton":
        problems.append(
            f"{card['id']}: card is a skeleton — capabilities not verified, "
            "verify before spending credits")
    return problems
```

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_models.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```powershell
git add scripts/factory/models.py tests/test_models.py
git commit -m "feat: model knowledge cards parsing and capability validation"
```

---

### Task 7: factory/shots.py — валидация плана съёмки

**Files:**
- Create: `scripts/factory/shots.py`
- Test: `tests/test_shots.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_shots.py`:
```python
import json
import pytest
from factory.shots import load_shots, ShotsError


def write(tmp_path, data):
    p = tmp_path / "shots.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


GOOD = {
    "episode": "ep01",
    "frames": [
        {"n": 1, "prompt": "cat in corridor"},
        {"n": 2, "prompt": "cat at panel", "refs": ["bible/characters/kepler-ref.png"]},
        {"n": 3, "prompt": "cat presses button"},
    ],
    "segments": [
        {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "cat walks"},
        {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "cat reaches"},
    ],
}


def test_valid_plan_loads(tmp_path):
    (tmp_path / "bible" / "characters").mkdir(parents=True)
    (tmp_path / "bible" / "characters" / "kepler-ref.png").write_bytes(b"x")
    data = load_shots(write(tmp_path, GOOD), tmp_path)
    assert len(data["frames"]) == 3


def test_broken_chain_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"][1] = {"n": 2, "start_frame": 1, "end_frame": 3, "prompt": "x"}
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="must chain frames"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_missing_ref_raises(tmp_path):
    with pytest.raises(ShotsError, match="missing ref"):
        load_shots(write(tmp_path, GOOD), tmp_path)  # png не создан


def test_frame_gap_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["frames"][2]["n"] = 5
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="without gaps"):
        load_shots(write(tmp_path, bad), tmp_path)


def test_segment_count_mismatch_raises(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["segments"] = bad["segments"][:1]
    bad["frames"][1].pop("refs")
    with pytest.raises(ShotsError, match="require 2 segments"):
        load_shots(write(tmp_path, bad), tmp_path)
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_shots.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.shots'`

- [ ] **Step 3: Реализация**

`scripts/factory/shots.py`:
```python
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
    numbers = {f["n"] for f in frames}
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
        expected = (s["n"], s["n"] + 1)
        if (s["start_frame"], s["end_frame"]) != expected:
            raise ShotsError(
                f"segment {s['n']}: must chain frames "
                f"{expected[0]}->{expected[1]}, "
                f"got {s['start_frame']}->{s['end_frame']}")
        if not s.get("prompt"):
            raise ShotsError(f"segment {s['n']}: empty prompt")

    if segments and len(segments) != len(frames) - 1:
        raise ShotsError(
            f"{len(frames)} frames require {len(frames) - 1} segments, "
            f"got {len(segments)}")
    return data
```

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_shots.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```powershell
git add scripts/factory/shots.py tests/test_shots.py
git commit -m "feat: shots.json validation with frame-chaining invariant"
```

---

### Task 8: factory/higgsfield_client.py — адаптер CLI

**Files:**
- Create: `scripts/factory/higgsfield_client.py`
- Test: `tests/test_higgsfield_client.py`
- Read first: `knowledge/higgsfield-cli.md` — **точные субкоманды и флаги взять оттуда**; в коде ниже они собраны в словарь `CMD`, поменять только его.

- [ ] **Step 1: Написать падающий тест**

`tests/test_higgsfield_client.py`:
```python
import json
import pytest
from factory import higgsfield_client as hf


def patch_run(monkeypatch, stdout="{}", returncode=0, stderr=""):
    calls = []

    class P:
        pass

    def fake_run(args, capture_output, text):
        calls.append(args)
        p = P()
        p.returncode, p.stdout, p.stderr = returncode, stdout, stderr
        return p

    monkeypatch.setattr(hf.subprocess, "run", fake_run)
    return calls


def test_estimate_parses_credits(monkeypatch):
    patch_run(monkeypatch, stdout=json.dumps({"credits": 3.5}))
    assert hf.estimate("kling-2.0", {"prompt": "x"}) == 3.5


def test_submit_returns_job_id(monkeypatch):
    calls = patch_run(monkeypatch, stdout=json.dumps({"job_id": "j-1"}))
    assert hf.submit("kling-2.0", {"prompt": "x"}) == "j-1"
    assert calls[0][0] == hf.CLI  # вызвали именно higgsfield CLI


def test_nonzero_exit_raises(monkeypatch):
    patch_run(monkeypatch, returncode=1, stderr="quota exceeded")
    with pytest.raises(hf.HiggsfieldError, match="quota exceeded"):
        hf.poll("j-1")


def test_wait_polls_until_completed(monkeypatch):
    answers = [{"status": "processing"}, {"status": "completed", "url": "u"}]
    monkeypatch.setattr(hf, "poll", lambda j: answers.pop(0))
    monkeypatch.setattr(hf.time, "sleep", lambda s: None)
    assert hf.wait("j-1")["status"] == "completed"


def test_download_checks_file_exists(monkeypatch, tmp_path):
    patch_run(monkeypatch)  # CLI «отработал», но файла нет
    with pytest.raises(hf.HiggsfieldError, match="missing"):
        hf.download("j-1", tmp_path / "out.png")
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_higgsfield_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.higgsfield_client'`

- [ ] **Step 3: Реализация**

`scripts/factory/higgsfield_client.py`:
```python
"""Адаптер Higgsfield CLI.

ЕДИНСТВЕННОЕ место в коде, где живут точные субкоманды/флаги CLI.
Источник правды — knowledge/higgsfield-cli.md (результат спайка, Task 2).
Если фактический синтаксис отличается от значений CMD ниже — поменять CMD,
остальной код и тесты не трогать.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

CLI = "higgsfield"  # имя бинаря; сверить со спайком

# Шаблоны субкоманд: {model}, {params}, {job_id}, {dest} подставляются .format()
CMD = {
    "estimate": ["generate", "cost", "--model", "{model}", "--params", "{params}"],
    "submit":   ["generate", "create", "--model", "{model}", "--params", "{params}"],
    "poll":     ["generate", "get", "{job_id}"],
    "download": ["generate", "download", "{job_id}", "--output", "{dest}"],
}


class HiggsfieldError(RuntimeError):
    pass


def _run(template: list[str], **kw) -> dict:
    args = [CLI] + [part.format(**kw) for part in template]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise HiggsfieldError(
            f"{' '.join(args)} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"raw": proc.stdout}


def estimate(model: str, params: dict) -> float:
    out = _run(CMD["estimate"], model=model, params=json.dumps(params))
    return float(out["credits"])


def submit(model: str, params: dict) -> str:
    out = _run(CMD["submit"], model=model, params=json.dumps(params))
    return out["job_id"]


def poll(job_id: str) -> dict:
    return _run(CMD["poll"], job_id=job_id)


def wait(job_id: str, timeout_sec: int = 1800, interval_sec: int = 10) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        out = poll(job_id)
        if out.get("status") in ("completed", "failed"):
            return out
        time.sleep(interval_sec)
    raise HiggsfieldError(f"job {job_id}: timeout after {timeout_sec}s")


def download(job_id: str, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(CMD["download"], job_id=job_id, dest=str(dest))
    if not dest.exists():
        raise HiggsfieldError(
            f"download reported success but {dest} is missing")
    return dest
```

После написания: сверить `CLI` и `CMD` с `knowledge/higgsfield-cli.md` и поправить под фактический синтаксис.

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_higgsfield_client.py -q`
Expected: `5 passed`

- [ ] **Step 5: Живой smoke-тест адаптера (одна дешёвая генерация)**

```powershell
python -c "from factory import higgsfield_client as hf; print(hf.estimate('<nano-banana-2-id>', {'prompt': 'orange cartoon cat, flat 2D'}))"
```
(запускать из корня с активированным venv; `$env:PYTHONPATH='scripts'` при необходимости)
Expected: число кредитов без исключений. Если упало — чинить `CMD` по higgsfield-cli.md.

- [ ] **Step 6: Commit**

```powershell
git add scripts/factory/higgsfield_client.py tests/test_higgsfield_client.py
git commit -m "feat: higgsfield CLI adapter (estimate/submit/wait/download)"
```

---

### Task 9: scripts/generate_batch.py — оркестратор

**Files:**
- Create: `scripts/generate_batch.py`
- Test: `tests/test_generate_batch.py`

- [ ] **Step 1: Написать падающий тест**

`tests/test_generate_batch.py`:
```python
import json
from pathlib import Path

import pytest

import generate_batch as gb
from factory.manifest import Manifest

KLING_CARD = (
    "---\nid: kling-2.0\ntype: video\nfamily: kling\nstatus: verified\n"
    "supports_start_end_frame: true\nnative_audio: false\n"
    "max_clip_seconds: 10\ncost_tier: low\n---\n# Kling\n")


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Мини-проект: 3 кадра, 2 отрезка; CWD = tmp_path (как корень репо)."""
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": "nano-banana-2", "video": "kling-2.0"},
    }), encoding="utf-8")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                   {"n": 3, "prompt": "c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    kdir = tmp_path / "knowledge" / "video"
    kdir.mkdir(parents=True)
    (kdir / "kling-2.0.md").write_text(KLING_CARD, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return pdir


def fake_hf(monkeypatch):
    calls = {"submitted": []}
    monkeypatch.setattr(gb.hf, "estimate", lambda m, p: 2.0)

    def submit(model, params):
        calls["submitted"].append(params)
        return f"job-{len(calls['submitted'])}"

    monkeypatch.setattr(gb.hf, "submit", submit)
    monkeypatch.setattr(gb.hf, "wait", lambda j: {"status": "completed"})

    def download(job_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"x")
        return Path(dest)

    monkeypatch.setattr(gb.hf, "download", download)
    return calls


def run(proj, stage):
    return gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", stage, "--yes"])


def test_happy_path_storyboard(proj, monkeypatch):
    calls = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(calls["submitted"]) == 3
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "done"
    assert (proj / "episodes" / "ep01" / "storyboard" / "001.png").exists()


def test_resume_skips_done(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert calls2["submitted"] == []  # ничего не сгенерировано повторно


def test_segments_pass_start_end_frames(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(calls2["submitted"]) == 2
    assert "start_frame" in calls2["submitted"][0]
    assert "end_frame" in calls2["submitted"][0]


def test_skeleton_card_blocks_segments(proj, monkeypatch):
    fake_hf(monkeypatch)
    card = Path("knowledge/video/kling-2.0.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run(proj, "segments") == 2  # валидация остановила ДО траты кредитов
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `pytest tests/test_generate_batch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate_batch'`

- [ ] **Step 3: Реализация**

`scripts/generate_batch.py`:
```python
"""Батч-генерация кадров или видеоотрезков по shots.json (спека §8).

Запускать из корня репозитория:
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage storyboard
  python scripts/generate_batch.py --project projects/pilot --episode ep01 --stage segments
Флаг --yes пропускает подтверждение сметы (для тестов/автоматизации).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory import higgsfield_client as hf
from factory.manifest import Manifest
from factory.models import find_card, validate_video_model
from factory.project import load_project
from factory.shots import load_shots

KNOWLEDGE_DIR = Path("knowledge")  # относительный путь — запуск из корня репо


def build_jobs(stage: str, shots: dict, project, episode_dir: Path) -> list[dict]:
    ep = shots["episode"]
    aspect = "9:16" if project.type == "shorts" else "16:9"
    jobs = []
    if stage == "storyboard":
        for f in shots["frames"]:
            jobs.append({
                "item_id": f"{ep}/storyboard/{f['n']:03d}",
                "kind": "frame",
                "model": project.models["image"],
                "dest": episode_dir / "storyboard" / f"{f['n']:03d}.png",
                "params": {"prompt": f["prompt"], "refs": f.get("refs", []),
                           "aspect_ratio": aspect},
            })
    else:  # segments
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
    return jobs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--stage", required=True, choices=["storyboard", "segments"])
    ap.add_argument("--yes", action="store_true",
                    help="не спрашивать подтверждение сметы")
    args = ap.parse_args(argv)

    project_dir = Path(args.project)
    project = load_project(project_dir / "project.json")
    episode_dir = project_dir / "episodes" / args.episode
    shots = load_shots(episode_dir / "shots.json", project_dir)
    manifest = Manifest(project_dir / "manifest.json")

    # Спека §6: валидация модели ДО траты кредитов
    if args.stage == "segments":
        card = find_card(KNOWLEDGE_DIR, project.models["video"])
        problems = validate_video_model(card, project.segment_seconds)
        if problems:
            print("МОДЕЛЬ НЕ ПРОШЛА ВАЛИДАЦИЮ — генерация не запущена:")
            for p in problems:
                print(f"  - {p}")
            return 2

    jobs = build_jobs(args.stage, shots, project, episode_dir)
    for j in jobs:
        manifest.add(j["item_id"], kind=j["kind"])
    manifest.save()

    todo = [j for j in jobs
            if manifest.get(j["item_id"])["status"] == "pending"]
    if not todo:
        print("Всё уже сгенерировано — нечего делать.")
        return 0

    # Спека §8 шаг 2: смета перед запуском
    estimates = {j["item_id"]: hf.estimate(j["model"], j["params"])
                 for j in todo}
    total = sum(estimates.values())
    print(f"СМЕТА: {len(todo)} генераций, ~{total:.0f} кредитов "
          f"({args.stage}, модель {todo[0]['model']}).")
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
        try:
            job_id = hf.submit(j["model"], j["params"])
            result = hf.wait(job_id)
            if result.get("status") != "completed":
                raise hf.HiggsfieldError(
                    str(result.get("error", "generation failed")))
            hf.download(job_id, j["dest"])
            manifest.set_status(
                j["item_id"], "done", file=str(j["dest"]), job_id=job_id,
                credits_spent=item["credits_spent"] + estimates[j["item_id"]])
            ok += 1
        except hf.HiggsfieldError as e:
            # технический сбой -> вернуть в очередь (спека §13)
            manifest.set_status(j["item_id"], "pending")
            print(f"  ! {j['item_id']}: {e}")
            fail += 1
        manifest.save()

    print(f"ИТОГ: готово {ok}, сбоев {fail}; "
          f"всего по проекту потрачено {manifest.credits_total():.0f} кредитов.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Тесты зелёные**

Run: `pytest tests/test_generate_batch.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```powershell
git add scripts/generate_batch.py tests/test_generate_batch.py
git commit -m "feat: batch generation orchestrator (estimate -> confirm -> generate -> manifest)"
```

---

### Task 10: Финал фазы — полный прогон и боевой мини-тест

**Files:**
- Modify: при необходимости — всё, что вскрылось

- [ ] **Step 1: Полный тестовый прогон**

Run: `pytest -q`
Expected: `~23 passed` (все задачи), ноль failed.

- [ ] **Step 2: Боевой мини-прогон (стоит кредитов — спросить подтверждение пользователя)**

Создать руками игрушечный проект `projects/_smoke/` (project.json + shots.json на 2 кадра и 1 отрезок, промпты — кот-космонавт из спайка) и прогнать:
```powershell
python scripts/generate_batch.py --project projects/_smoke --episode ep01 --stage storyboard
python scripts/generate_batch.py --project projects/_smoke --episode ep01 --stage segments
```
Expected: смета напечатана, после подтверждения — 2 png + 1 mp4 на диске, manifest.json со статусами done, повторный запуск отвечает «Всё уже сгенерировано».

- [ ] **Step 3: Commit + итог фазы**

```powershell
git add -A; git commit -m "test: phase 1 smoke project"
```
Доложить пользователю: фактическая стоимость smoke-прогона в кредитах, замеченные ограничения CLI, готовность к фазе 2 (звук и сборка).

---

## Самопроверка плана (выполнена)

- **Покрытие спеки (скоуп фазы 1):** §3 архитектура — Tasks 1, 3–9; §4 структура проекта и нумерация — Tasks 3, 7, 9; §6 карточки и валидация — Tasks 5, 6; §8 механика (план → смета → батч → манифест) — Tasks 7–9; §10 манифест — Task 4; §13 техсбои — Task 9 (возврат в pending); §14 спайк — Task 2. Ревью кадров (§9) — это работа Claude-режиссёра, не скриптов: фаза 3. Звук/сборка (§11–12) — фаза 2.
- **Плейсхолдеры:** скелеты карточек — осознанная политика спеки §6, не плейсхолдер плана; флаги CLI собраны в один словарь `CMD` с явным источником правды (спайк-документ).
- **Согласованность типов:** `Manifest.set_status/add/pending/credits_total`, `load_project().segment_seconds/models`, `find_card/validate_video_model`, `hf.estimate/submit/wait/download` — сигнатуры в Tasks 4–9 сверены, тесты используют те же имена.
