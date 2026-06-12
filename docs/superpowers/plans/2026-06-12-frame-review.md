# Ревью кадров (отклонение и перегенерация) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Встроить этап ревью в жизненный цикл генераций: новый статус `generated`, review-CLI для приёмки/отклонения, автоперегенерация отклонённых с лимитом, жёсткий гейт стадии segments.

**Architecture:** Машина статусов в `factory/manifest.py` получает промежуточный статус `generated` («скачано, ждёт ревью») и счётчик `reject_count`; оркестратор `generate_batch.py` завершает генерации в `generated`, перед батчем автоматически возвращает отклонённые в очередь (до лимита `max_rejections`) и блокирует стадию segments до приёмки кадров (exit 3); новый `scripts/review.py` — CLI ревьюера поверх `Manifest.set_status`, без собственной логики переходов.

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, stdlib only (json/argparse/pathlib).

**Спека:** `docs/superpowers/specs/2026-06-12-frame-review-design.md` (утверждена 2026-06-12).

**Правила репо (обязательны):**
- Рабочая директория — корень репо `C:\Users\lar\content-factory`, ветка `phase-1-generation`.
- Тесты гонять строго как `.\.venv\Scripts\python.exe -m pytest -q` (venv НЕ активировать).
- Перед коммитом весь набор тестов зелёный. На момент старта: **73 passed**.
- Кредиты Higgsfield не нужны: всё мокается, реальный CLI не вызывать.

---

## Структура файлов

| Файл | Действие | Ответственность |
|---|---|---|
| `scripts/factory/manifest.py` | Modify | машина статусов: + `generated`, + `reject_count`, автоинкремент |
| `scripts/factory/project.py` | Modify | поле брифа `max_rejections` (дефолт 2) |
| `scripts/generate_batch.py` | Modify | завершение в `generated`, автоперевод rejected→pending, гейт segments (exit 3), idle-сообщение |
| `scripts/review.py` | Create | CLI ревьюера: list/accept/accept-notes/reject/requeue |
| `tests/test_manifest.py` | Modify | новые переходы + обновить тесты под новую машину |
| `tests/test_project.py` | Modify | + тесты max_rejections |
| `tests/test_generate_batch.py` | Modify | generated-путь, автоперевод, лимит, гейт |
| `tests/test_review.py` | Create | тесты review-CLI |

---

### Task 1: manifest.py — статус `generated` и `reject_count`

**Files:**
- Modify: `scripts/factory/manifest.py`
- Test: `tests/test_manifest.py`

Новая машина (спека ревью §3): `pending → generating → generated | pending(техсбой)`; ревью: `generated → done | accepted_with_notes | rejected`; `rejected → pending`; `accepted_with_notes → pending`; `done` терминален (= принято ревью). Прямые `generating → done/rejected/accepted_with_notes` удаляются. `reject_count` инкрементируется автоматически в `set_status` при каждом переходе в `rejected`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_manifest.py` ДОБАВИТЬ в конец файла:

```python
def review_ready(m, item_id="x", kind="frame"):
    """Довести item до generated (готов к ревью)."""
    m.add(item_id, kind=kind)
    m.set_status(item_id, "generating")
    m.set_status(item_id, "generated", file=f"{item_id}.png")


def test_generation_ends_in_generated_then_review_accepts(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    assert m.get("x")["status"] == "generated"
    m.set_status("x", "done")  # ревью: принято
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")  # done терминален


def test_generating_to_done_directly_is_forbidden(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "done")


def test_generating_to_rejected_directly_is_forbidden(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "rejected", reject_reason="r")


def test_reject_count_increments_automatically(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    assert m.get("x")["reject_count"] == 0
    m.set_status("x", "rejected", reject_reason="anatomy")
    assert m.get("x")["reject_count"] == 1
    m.set_status("x", "pending")
    m.set_status("x", "generating")
    m.set_status("x", "generated")
    m.set_status("x", "rejected", reject_reason="style")
    assert m.get("x")["reject_count"] == 2


def test_accepted_with_notes_allows_requeue(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    m.set_status("x", "accepted_with_notes", notes="фон темноват")
    m.set_status("x", "pending")
    assert m.get("x")["status"] == "pending"
```

И ОБНОВИТЬ три существующих теста под новую машину (путь к `done` теперь только через `generated`):

```python
def test_done_is_terminal(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    m.set_status("x", "generated", file="x.png")
    m.set_status("x", "done")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")


def test_rejected_requires_reason(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    m.set_status("x", "generated")
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
    m.set_status("a", "generated", file="a.png", credits_spent=2.0)
    m.set_status("a", "done")
    m.save()

    m2 = Manifest(path)  # перечитываем с диска
    assert m2.pending() == ["b"]
    assert m2.pending(kind="frame") == []
    assert m2.credits_total() == 2.0
```

В `test_unknown_field_raises` заменить переход `"done"` на `"generated"` (прямой `generating → done` теперь запрещён, а тест должен падать на unknown field, не на переходе):

```python
def test_unknown_field_raises(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="unknown fields"):
        m.set_status("x", "generated", fiel="typo.png")
```

- [ ] **Step 2: Прогнать тесты — новые должны упасть**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -q`
Expected: FAIL — `unknown status: 'generated'` в новых/обновлённых тестах.

- [ ] **Step 3: Реализация в `scripts/factory/manifest.py`**

Заменить докстринг модуля, `STATUSES`, `KNOWN_FIELDS`, `ALLOWED`:

```python
"""Манифест проекта — память завода (спека §10; машина ревью — спека
docs/superpowers/specs/2026-06-12-frame-review-design.md §3).

Статусы: pending -> generating -> generated (ждёт ревью) | pending (техсбой).
Ревью: generated -> done | accepted_with_notes | rejected.
rejected/accepted_with_notes -> pending = перегенерация.
done = принято ревью, терминален.
reject_count инкрементируется автоматически при каждом переходе в rejected.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATUSES = {"pending", "generating", "generated", "done", "rejected",
            "accepted_with_notes"}
KNOWN_FIELDS = {"file", "job_id", "credits_spent", "reject_reason", "notes",
                "attempts", "reject_count"}
ALLOWED = {
    "pending": {"generating"},
    "generating": {"generated", "pending"},
    "generated": {"done", "accepted_with_notes", "rejected"},
    "rejected": {"pending"},
    "accepted_with_notes": {"pending"},
    "done": set(),
}
```

В `add()` добавить дефолт `"reject_count": 0`:

```python
    def add(self, item_id: str, kind: str) -> None:
        self.data["items"].setdefault(item_id, {
            "kind": kind, "status": "pending", "attempts": 0,
            "credits_spent": 0.0, "file": None, "job_id": None,
            "reject_reason": None, "notes": None, "reject_count": 0,
        })
```

В `set_status()` перед `item.update(...)` добавить автоинкремент (`.get` — совместимость со старыми манифестами без поля):

```python
        if status == "rejected" and not fields.get("reject_reason"):
            raise ManifestError(f"{item_id}: rejected requires reject_reason")
        if status == "rejected":
            fields["reject_count"] = item.get("reject_count", 0) + 1
        item.update(status=status, **fields)
```

- [ ] **Step 4: Прогнать тесты модуля — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -q`
Expected: PASS (все).

- [ ] **Step 5: Полный набор — есть ОЖИДАЕМЫЕ падения в test_generate_batch.py**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: тесты `tests/test_generate_batch.py` упадут (`generating -> done is not allowed`) — оркестратор чинится в Task 3. Это известное межзадачное состояние: Task 1 и Task 3 меняют один контракт. УБЕДИТЬСЯ, что других падений нет (test_manifest, test_project, test_models, test_shots, test_higgsfield_client — зелёные).

- [ ] **Step 6: Commit**

```powershell
git add scripts/factory/manifest.py tests/test_manifest.py
git commit -m "feat: review state machine — generated status + reject_count autoincrement"
```

---

### Task 2: project.py — поле `max_rejections`

**Files:**
- Modify: `scripts/factory/project.py`
- Test: `tests/test_project.py`

Опциональное поле брифа `max_rejections`: целое ≥ 0, дефолт 2 (спека ревью §6).

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_project.py` добавить в конец:

```python
def test_max_rejections_default(tmp_path):
    p = load_project(write(tmp_path, BASE))
    assert p.max_rejections == 2


def test_max_rejections_custom(tmp_path):
    p = load_project(write(tmp_path, {**BASE, "max_rejections": 5}))
    assert p.max_rejections == 5


def test_max_rejections_invalid_raises(tmp_path):
    for bad in (-1, "2", 1.5, True):
        with pytest.raises(ProjectError, match="max_rejections"):
            load_project(write(tmp_path, {**BASE, "max_rejections": bad}))
```

- [ ] **Step 2: Прогнать — падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project.py -q`
Expected: FAIL — `TypeError`/`AttributeError` (поля нет).

- [ ] **Step 3: Реализация в `scripts/factory/project.py`**

В dataclass `Project` добавить поле ПЕРЕД `raw`:

```python
    review_strictness: str
    max_rejections: int
    raw: dict
```

В `load_project` после блока `strictness` добавить валидацию и передать поле в конструктор:

```python
    max_rejections = data.get("max_rejections", 2)
    if (isinstance(max_rejections, bool) or not isinstance(max_rejections, int)
            or max_rejections < 0):
        raise ProjectError(
            f"max_rejections must be a non-negative int, got {max_rejections!r}")

    return Project(
        name=data["name"], type=ptype, theme=data["theme"],
        language=data.get("language", "en"), models=data["models"],
        quality_mode=quality, review_strictness=strictness,
        max_rejections=max_rejections, raw=data,
    )
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_project.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add scripts/factory/project.py tests/test_project.py
git commit -m "feat: project.json max_rejections (review regeneration limit, default 2)"
```

---

### Task 3: generate_batch.py — завершение в `generated`, автоперевод rejected, idle-сообщение

**Files:**
- Modify: `scripts/generate_batch.py`
- Test: `tests/test_generate_batch.py`

Спека ревью §4.1, §4.2, §4.4: успешная генерация → `generated`; перед батчем `rejected` с `reject_count < project.max_rejections` → `pending` (перегенерация по актуальному shots.json — jobs и так строятся из него каждый запуск), достигшие лимита пропускаются с громким сообщением; если генерировать нечего, но есть `generated` — сообщить «ждут ревью».

- [ ] **Step 1: Обновить существующие тесты под `generated`**

В `tests/test_generate_batch.py`:

В `test_happy_path_storyboard` заменить ожидание статуса:

```python
    assert m.get("ep01/storyboard/001")["status"] == "generated"
```

В `test_recover_stuck_generating_item` заменить последнюю строку:

```python
    assert m2.get("ep01/storyboard/001")["status"] == "generated"
```

Переименовать `test_resume_skips_done` → `test_resume_skips_generated` (тело без изменений — повторный прогон не генерирует повторно).

`test_segments_pass_start_end_frames` пока НЕ трогать — он сломается только в Task 4 (гейт) и будет обновлён там.

- [ ] **Step 2: Написать падающие тесты на новое поведение**

Добавить в конец `tests/test_generate_batch.py`:

```python
def reject(proj, item_id, reason="не по сценарию"):
    m = Manifest(proj / "manifest.json")
    m.set_status(item_id, "rejected", reject_reason=reason)
    m.save()


def set_max_rejections(proj, value):
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["max_rejections"] = value
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")


def test_rejected_autorequeued_and_regenerated(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(calls2["submitted"]) == 1  # перегенерирован только отклонённый
    m = Manifest(proj / "manifest.json")
    item = m.get("ep01/storyboard/001")
    assert item["status"] == "generated"
    assert item["reject_count"] == 1  # журнал отклонений не сбрасывается


def test_reject_limit_blocks_regeneration(proj, monkeypatch, capsys):
    set_max_rejections(proj, 1)
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert calls2["submitted"] == []  # лимит достигнут — не перегенерируем
    out = capsys.readouterr().out
    assert "ЛИМИТ ОТКЛОНЕНИЙ" in out
    assert "ep01/storyboard/001" in out
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "rejected"


def test_idle_run_reports_awaiting_review(proj, monkeypatch, capsys):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    capsys.readouterr()  # сбросить вывод первого прогона
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert calls2["submitted"] == []
    assert "ждут ревью" in capsys.readouterr().out
```

- [ ] **Step 3: Прогнать — новые и обновлённые падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: FAIL (оркестратор ещё ставит `done`, переход запрещён машиной из Task 1).

- [ ] **Step 4: Реализация в `scripts/generate_batch.py`**

4a. В `main()` после блока восстановления зависших `generating` (строки `recovered = ...` … `manifest.save()`) добавить автоперевод отклонённых:

```python
    # Цикл ревью (спека ревью §4.2): отклонённые уходят на перегенерацию по
    # актуальному shots.json, пока не исчерпан лимит max_rejections; дальше —
    # решение человека (review.py requeue).
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
```

4b. Заменить idle-ветку:

```python
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
```

4c. В цикле генерации заменить успешное завершение `"done"` → `"generated"`:

```python
            manifest.set_status(
                j["item_id"], "generated", file=str(j["dest"]), job_id=job_id,
                credits_spent=item["credits_spent"] + estimates[j["item_id"]])
```

4d. Обновить итоговый print:

```python
    print(f"ИТОГ: сгенерировано {ok} (ждут ревью), сбоев {fail}; "
          f"всего по проекту потрачено {manifest.credits_total():.0f} кредитов.")
```

4e. Обновить докстринг модуля — добавить строку после описания флага `--yes`:

```
Успешные генерации получают статус generated и ждут ревью (scripts/review.py).
```

- [ ] **Step 5: Прогнать тесты модуля — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: PASS (все, включая существующие про сбои/restore/refs).

- [ ] **Step 6: Полный набор — зелёный**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS (падения Task 1 Step 5 устранены).

- [ ] **Step 7: Commit**

```powershell
git add scripts/generate_batch.py tests/test_generate_batch.py
git commit -m "feat: batch ends in generated; auto-requeue rejected under max_rejections"
```

---

### Task 4: generate_batch.py — гейт segments (exit 3)

**Files:**
- Modify: `scripts/generate_batch.py`
- Test: `tests/test_generate_batch.py`

Спека ревью §4.3: при `--stage segments`, до сметы и любых трат, все кадры из `start_frame`/`end_frame` отрезков должны существовать в манифесте со статусом `done` или `accepted_with_notes`; иначе список проблемных + exit 3. Код 2 остаётся за валидацией модели (она выполняется ПЕРВОЙ — порядок закреплён существующими тестами skeleton-карточки).

- [ ] **Step 1: Написать падающие тесты + обновить затронутый**

В `tests/test_generate_batch.py` добавить хелпер и тесты:

```python
def accept_frames(proj, status="done"):
    m = Manifest(proj / "manifest.json")
    for item_id in list(m.data["items"]):
        if m.get(item_id)["status"] == "generated":
            m.set_status(item_id, status)
    m.save()


def test_segments_blocked_until_frames_accepted(proj, monkeypatch, capsys):
    fake_hf(monkeypatch)
    run(proj, "storyboard")  # кадры в generated — ревью не пройдено
    estimate_called = []
    monkeypatch.setattr(gb.hf, "estimate",
                        lambda m, p: estimate_called.append(1) or 2.0)
    assert run(proj, "segments") == 3
    assert estimate_called == []  # заблокировано ДО сметы и трат
    out = capsys.readouterr().out
    assert "заблокирована" in out
    assert "ep01/storyboard/001" in out


def test_segments_blocked_when_frames_never_generated(proj, monkeypatch, capsys):
    fake_hf(monkeypatch)
    assert run(proj, "segments") == 3  # storyboard вообще не запускался
    assert "не генерировался" in capsys.readouterr().out


def test_segments_pass_with_accepted_with_notes(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    accept_frames(proj, status="accepted_with_notes")
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(calls2["submitted"]) == 2
```

Обновить `test_segments_pass_start_end_frames` — после прогона storyboard принять кадры:

```python
def test_segments_pass_start_end_frames(proj, monkeypatch):
    fake_hf(monkeypatch)
    run(proj, "storyboard")
    accept_frames(proj)
    calls2 = fake_hf(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(calls2["submitted"]) == 2
    assert "start_frame" in calls2["submitted"][0]
    assert "end_frame" in calls2["submitted"][0]
```

- [ ] **Step 2: Прогнать — новые падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: FAIL — гейта нет, `test_segments_blocked_until_frames_accepted` получает 0 вместо 3 (а старый `test_segments_pass_start_end_frames` уже зелёный с accept_frames).

- [ ] **Step 3: Реализация**

3a. В `scripts/generate_batch.py` обновить импорт:

```python
from factory.manifest import Manifest, ManifestError
```

3b. В `main()` внутри блока `if args.stage == "segments":` СРАЗУ ПОСЛЕ существующей валидации модели (после `return 2`) добавить:

```python
        # Чекпоинт ревью (спека ревью §4.3): отрезки строятся только на
        # принятых кадрах — done или accepted_with_notes.
        accepted = {"done", "accepted_with_notes"}
        problems = {}
        for s in shots["segments"]:
            for n in (s["start_frame"], s["end_frame"]):
                frame_id = f"{shots['episode']}/storyboard/{n:03d}"
                if frame_id in problems:
                    continue
                try:
                    status = manifest.get(frame_id)["status"]
                except ManifestError:
                    problems[frame_id] = "не генерировался"
                    continue
                if status not in accepted:
                    problems[frame_id] = f"статус {status}"
        if problems:
            print("КАДРЫ НЕ ПРИНЯТЫ РЕВЬЮ — стадия segments заблокирована:")
            for frame_id in sorted(problems):
                print(f"  - {frame_id}: {problems[frame_id]}")
            return 3
```

3c. В докстринг модуля добавить строку про коды выхода:

```
Коды выхода: 0 успех; 1 сбои/отмена; 2 модель не прошла валидацию;
3 segments заблокирован — кадры не приняты ревью.
```

- [ ] **Step 4: Прогнать тесты модуля — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q`
Expected: PASS, в т.ч. `test_skeleton_card_blocks_segments` (== 2: валидация модели по-прежнему раньше гейта).

- [ ] **Step 5: Полный набор — зелёный**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/generate_batch.py tests/test_generate_batch.py
git commit -m "feat: segments gate — frames must pass review, exit code 3"
```

---

### Task 5: scripts/review.py — CLI ревьюера

**Files:**
- Create: `scripts/review.py`
- Create: `tests/test_review.py`

Спека ревью §5. Все изменения статусов — только через `Manifest.set_status` (валидация переходов в одном месте). При `ManifestError` — сообщение в stderr, exit 1, манифест НЕ сохраняется (на диске ничего не меняется — «всё или ничего»).

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_review.py`:

```python
"""Тесты review-CLI (спека ревью §5)."""
import pytest

import review
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path):
    """Проект с манифестом: 001 в generated (ждёт ревью), 002 в pending."""
    pdir = tmp_path / "projects" / "pilot"
    pdir.mkdir(parents=True)
    m = Manifest(pdir / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated", file="001.png")
    m.add("ep01/storyboard/002", kind="frame")
    m.save()
    return pdir


def run(proj, *args):
    return review.main(["--project", str(proj), *args])


def test_accept_moves_generated_to_done(proj):
    assert run(proj, "accept", "ep01/storyboard/001") == 0
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "done"


def test_accept_is_all_or_nothing(proj, capsys):
    # 002 в pending -> переход запрещён; 001 НЕ должен сохраниться как done
    assert run(proj, "accept", "ep01/storyboard/001",
               "ep01/storyboard/002") == 1
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "generated"
    assert "not allowed" in capsys.readouterr().err


def test_accept_notes(proj):
    assert run(proj, "accept-notes", "ep01/storyboard/001",
               "--notes", "фон темноват") == 0
    m = Manifest(proj / "manifest.json")
    it = m.get("ep01/storyboard/001")
    assert it["status"] == "accepted_with_notes"
    assert it["notes"] == "фон темноват"


def test_reject_records_reason_and_count(proj):
    assert run(proj, "reject", "ep01/storyboard/001",
               "--reason", "anatomy") == 0
    m = Manifest(proj / "manifest.json")
    it = m.get("ep01/storyboard/001")
    assert it["status"] == "rejected"
    assert it["reject_reason"] == "anatomy"
    assert it["reject_count"] == 1


def test_reject_without_reason_fails(proj):
    with pytest.raises(SystemExit):  # argparse: --reason обязателен
        run(proj, "reject", "ep01/storyboard/001")


def test_requeue_works_even_past_limit(proj):
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/storyboard/001", "rejected", reject_reason="r1")
    m.data["items"]["ep01/storyboard/001"]["reject_count"] = 5  # за лимитом
    m.save()
    assert run(proj, "requeue", "ep01/storyboard/001") == 0
    m2 = Manifest(proj / "manifest.json")
    it = m2.get("ep01/storyboard/001")
    assert it["status"] == "pending"
    assert it["reject_count"] == 5  # журнал не сбрасывается


def test_unknown_id_returns_1(proj, capsys):
    assert run(proj, "accept", "nope") == 1
    assert "unknown item_id" in capsys.readouterr().err


def test_list_with_status_filter(proj, capsys):
    assert run(proj, "list", "--status", "generated") == 0
    out = capsys.readouterr().out
    assert "ep01/storyboard/001" in out
    assert "ep01/storyboard/002" not in out


def test_list_shows_all_without_filter(proj, capsys):
    assert run(proj, "list") == 0
    out = capsys.readouterr().out
    assert "ep01/storyboard/001" in out
    assert "ep01/storyboard/002" in out
```

- [ ] **Step 2: Прогнать — падают**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_review.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'review'`.

- [ ] **Step 3: Создать `scripts/review.py`**

```python
"""CLI ревью сгенерированных кадров и отрезков (спека ревью §5).

Для ревьюера — человека и Claude-режиссёра. Запускать из корня репозитория:
  python scripts/review.py --project projects/pilot list --status generated
  python scripts/review.py --project projects/pilot accept <id> [<id> ...]
  python scripts/review.py --project projects/pilot accept-notes <id> --notes "..."
  python scripts/review.py --project projects/pilot reject <id> --reason "..."
  python scripts/review.py --project projects/pilot requeue <id>

requeue — решение человека после лимита отклонений: возвращает rejected или
accepted_with_notes в pending; reject_count при этом НЕ сбрасывается (журнал).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.manifest import Manifest, ManifestError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="показать items манифеста")
    p_list.add_argument("--status", help="фильтр по статусу")

    p_accept = sub.add_parser("accept", help="generated -> done")
    p_accept.add_argument("ids", nargs="+")

    p_notes = sub.add_parser("accept-notes",
                             help="generated -> accepted_with_notes")
    p_notes.add_argument("id")
    p_notes.add_argument("--notes", required=True)

    p_reject = sub.add_parser("reject", help="generated -> rejected")
    p_reject.add_argument("id")
    p_reject.add_argument("--reason", required=True)

    p_requeue = sub.add_parser(
        "requeue", help="rejected | accepted_with_notes -> pending")
    p_requeue.add_argument("id")

    args = ap.parse_args(argv)
    manifest = Manifest(Path(args.project) / "manifest.json")

    if args.command == "list":
        for item_id in sorted(manifest.data["items"]):
            it = manifest.data["items"][item_id]
            if args.status and it["status"] != args.status:
                continue
            print(f"{item_id}\t{it['status']}\t"
                  f"attempts={it.get('attempts', 0)}\t"
                  f"rejects={it.get('reject_count', 0)}\t{it.get('file')}")
        return 0

    # Мутации — всё или ничего: при ошибке манифест не сохраняется
    try:
        if args.command == "accept":
            for item_id in args.ids:
                manifest.set_status(item_id, "done")
        elif args.command == "accept-notes":
            manifest.set_status(args.id, "accepted_with_notes",
                                notes=args.notes)
        elif args.command == "reject":
            manifest.set_status(args.id, "rejected",
                                reject_reason=args.reason)
        elif args.command == "requeue":
            manifest.set_status(args.id, "pending")
    except ManifestError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1
    manifest.save()
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [ ] **Step 4: Прогнать тесты модуля — зелёные**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_review.py -q`
Expected: PASS (все 10).

- [ ] **Step 5: Полный набор — зелёный**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add scripts/review.py tests/test_review.py
git commit -m "feat: review.py CLI — list/accept/accept-notes/reject/requeue"
```

---

### Task 6: Документация и финальная верификация

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-06-12-phase1-progress.md`

- [ ] **Step 1: CLAUDE.md — упомянуть review.py**

В разделе «Структура» после строки про generate_batch.py добавить:

```
- scripts/review.py — ревью генераций: accept/reject/requeue (статусы манифеста)
```

- [ ] **Step 1b: Старая спека — указатель на новую машину статусов**

В `docs/superpowers/specs/2026-06-11-content-factory-design.md` в начало раздела §10 (после строки заголовка «## 10. Манифест») добавить:

```
> **Поправка 2026-06-12:** машина статусов заменена машиной ревью — см.
> `2026-06-12-frame-review-design.md` §3 (новый статус `generated`, лимит
> перегенераций `max_rejections` = 2 вместо 3 из §8/§13).
```

- [ ] **Step 2: Прогресс-файл — зафиксировать итог фичи**

В `docs/superpowers/plans/2026-06-12-phase1-progress.md` в конец раздела «Следующая задача: отклонение кадров на ревью» добавить подраздел:

```markdown
### Итог (2026-06-12)

Фича реализована по спеке `docs/superpowers/specs/2026-06-12-frame-review-design.md`
и плану `docs/superpowers/plans/2026-06-12-frame-review.md` (subagent-driven).
Машина ревью: pending → generating → generated → done|accepted_with_notes|rejected;
done терминален (= принято ревью). review.py: list/accept/accept-notes/reject/requeue.
Гейт segments: exit 3. Лимит: max_rejections (project.json, дефолт 2).
Коммиты: <перечислить фактические хеши задач 1–5>. Тесты: <фактическое число> passed.
```

(Плейсхолдеры в угловых скобках заполнить фактическими значениями из `git log --oneline` и прогона pytest.)

- [ ] **Step 3: Финальный прогон всего набора**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS, ~97 тестов (73 стартовых + ~24 новых: 5 manifest, 3 project, 6 generate_batch, 10 review). Число записать в прогресс-файл.

- [ ] **Step 4: Commit**

```powershell
git add CLAUDE.md docs/superpowers/plans/2026-06-12-phase1-progress.md docs/superpowers/specs/2026-06-11-content-factory-design.md
git commit -m "docs: frame review feature — CLAUDE.md, spec amendment note, progress handoff"
```
