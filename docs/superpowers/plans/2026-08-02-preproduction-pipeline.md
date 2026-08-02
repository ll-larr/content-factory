# Пре-продакшн конвейера (бриф → shots.json) — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** построить первую половину конвейера — от заполненного `project.json` до `shots.json`, проходящего гейты `generate_batch.py`.

**Architecture:** Python владеет только механикой — состоянием одобрений, гейтами, разворачиванием плейсхолдеров и валидацией; творчество живёт в скиллах `.claude/skills/factory*`. Состояние одобрения хранится во frontmatter самого артефакта вместе с хешом тела и хешами зависимостей, поэтому правка утверждённого текста не проходит молча. Референсы персонажей — обычная платная генерация через существующий манифест и `review.py`.

**Tech Stack:** Python 3.12, pytest, PyYAML, hashlib (stdlib), ffmpeg — не нужен.

**Спека:** `docs/superpowers/specs/2026-08-02-preproduction-pipeline-design.md`

## Global Constraints

- Все команды — **из корня репо** `C:\Users\lar\content-factory`; пути `knowledge/` и `projects/` относительные.
- Тесты: `.\.venv\Scripts\python.exe -m pytest -q`. venv **не активировать** — всегда явный путь.
- Отправная точка: **235 passed**. Перед каждым коммитом набор зелёный, вывод чистый.
- Стиль репо: докстроки и комментарии по-русски, технические термины английские.
- Изоляция провайдера не нарушается: этот план не трогает `scripts/factory/providers/`.
- Гейт первой половины отдаёт **код возврата 3** — тот же, что у `generate_batch`/`mix_audio`/`assemble`.
- `status: approved` появляется **только** через `factory.py approve`. Ни скилл, ни другой код его не пишет.
- Живых вызовов API в тестах нет; сети нет.
- В конец тела коммита — `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Карта файлов

| Файл | Ответственность | Задача |
|---|---|---|
| `scripts/factory/artifact.py` | **новый** — чтение/запись frontmatter текстового артефакта, хеш тела | 1 |
| `tests/test_artifact.py` | **новый** | 1 |
| `scripts/factory/preprod.py` | **новый** — зависимости, состояние артефакта, гейты этапов, `next_stage` | 2, 3 |
| `tests/test_preprod.py` | **новый** | 2, 3 |
| `scripts/factory.py` | **новый** — CLI `init/status/check/approve/next/diff` | 4, 7 |
| `tests/test_factory_cli.py` | **новый** | 4, 7 |
| `scripts/factory/prompts.py` | **новый** — канонические блоки, плейсхолдеры, валидация промптов | 5 |
| `tests/test_prompts.py` | **новый** | 5 |
| `scripts/generate_batch.py` | разворачивание плейсхолдеров + стадия `characters` | 5, 6 |
| `tests/test_generate_batch.py` | тесты стадии `characters` и разворачивания | 5, 6 |
| `.claude/skills/factory-*/SKILL.md` | **новые** — процессы этапов и драйвер | 8 |
| `CLAUDE.md`, `README.md` | актуализация | 8 |

---

## Task 1: Текстовый артефакт — frontmatter и хеш тела

Фундамент всего: пока нет надёжного чтения/записи frontmatter и стабильного хеша тела, ни гейты, ни определение устаревания не построить.

`factory/models.py` уже парсит frontmatter карточек, но переиспользовать его нельзя: там тело документа незначимо и отбрасывается, а здесь тело — главное, по нему считается `content_sha`.

**Files:**
- Create: `scripts/factory/artifact.py`
- Test: `tests/test_artifact.py`

**Interfaces:**
- Produces: `Artifact` (dataclass: `path: Path`, `meta: dict`, `body: str`, свойство `sha: str`); `load_artifact(path) -> Artifact`; `save_artifact(art: Artifact) -> None`; `body_sha(body: str) -> str`; `ArtifactError(ValueError)`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_artifact.py`:

```python
"""Тесты текстового артефакта пре-продакшна (спека 2026-08-02 §4)."""
import pytest

from factory.artifact import (Artifact, ArtifactError, body_sha, load_artifact,
                              save_artifact)

SAMPLE = """---
kind: idea
status: draft
---

Космические коты исследуют заброшенную станцию.
"""


def test_load_reads_meta_and_body(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text(SAMPLE, encoding="utf-8")
    art = load_artifact(p)
    assert art.meta["kind"] == "idea"
    assert art.meta["status"] == "draft"
    assert "заброшенную станцию" in art.body


def test_save_load_round_trip(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text(SAMPLE, encoding="utf-8")
    art = load_artifact(p)
    art.meta["status"] = "approved"
    save_artifact(art)

    again = load_artifact(p)
    assert again.meta["status"] == "approved"
    assert again.sha == art.sha, "перезапись frontmatter не должна менять хеш тела"


def test_sha_ignores_line_endings(tmp_path):
    """CRLF на Windows не должен менять хеш — иначе файл 'устареет' сам собой."""
    assert body_sha("a\r\nb") == body_sha("a\nb")


def test_sha_ignores_edge_whitespace():
    assert body_sha("\n  текст  \n\n") == body_sha("текст")


def test_sha_changes_with_content():
    assert body_sha("текст один") != body_sha("текст два")


def test_missing_frontmatter_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("просто текст без шапки", encoding="utf-8")
    with pytest.raises(ArtifactError, match="frontmatter"):
        load_artifact(p)


def test_unclosed_frontmatter_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("---\nkind: idea\nтекст", encoding="utf-8")
    with pytest.raises(ArtifactError, match="не закрыт"):
        load_artifact(p)


def test_frontmatter_not_a_mapping_raises(tmp_path):
    p = tmp_path / "idea.md"
    p.write_text("---\n- a\n- b\n---\nтекст", encoding="utf-8")
    with pytest.raises(ArtifactError, match="словар"):
        load_artifact(p)


def test_save_creates_parent_dirs(tmp_path):
    art = Artifact(path=tmp_path / "bible" / "characters" / "murzik.md",
                   meta={"kind": "character"}, body="рыжий кот")
    save_artifact(art)
    assert art.path.exists()


def test_save_keeps_cyrillic_readable(tmp_path):
    art = Artifact(path=tmp_path / "idea.md",
                   meta={"kind": "idea", "note": "космос"}, body="тело")
    save_artifact(art)
    assert "космос" in art.path.read_text(encoding="utf-8")
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_artifact.py -q
```

Ожидание: FAIL — `ModuleNotFoundError: No module named 'factory.artifact'`.

- [ ] **Шаг 3: Реализовать**

Создать `scripts/factory/artifact.py`:

```python
"""Текстовый артефакт пре-продакшна: YAML-frontmatter + значимое тело.

Спека 2026-08-02 §4. От карточки модели (factory.models) отличается тем, что тело
здесь значимо: по нему считается content_sha, и правка тела после одобрения обязана
быть заметна гейту.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

_SEP = "---"


class ArtifactError(ValueError):
    pass


def body_sha(body: str) -> str:
    """sha256 тела. Нормализуем переводы строк и краевые пробелы: иначе один и тот же
    текст, сохранённый на Windows и в git, давал бы разные хеши и артефакт «устаревал»
    бы сам собой."""
    normalized = body.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class Artifact:
    path: Path
    meta: dict
    body: str

    @property
    def sha(self) -> str:
        return body_sha(self.body)


def load_artifact(path: Path) -> Artifact:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_SEP):
        raise ArtifactError(f"{path}: нет YAML-frontmatter")
    parts = text.split(_SEP, 2)
    if len(parts) < 3:
        raise ArtifactError(f"{path}: frontmatter не закрыт '{_SEP}'")
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise ArtifactError(f"{path}: некорректный YAML — {e}") from None
    if not isinstance(meta, dict):
        raise ArtifactError(f"{path}: frontmatter не является YAML-словарём")
    return Artifact(path=path, meta=meta, body=parts[2].strip())


def save_artifact(art: Artifact) -> None:
    front = yaml.safe_dump(art.meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    art.path.parent.mkdir(parents=True, exist_ok=True)
    art.path.write_text(f"{_SEP}\n{front}\n{_SEP}\n\n{art.body.strip()}\n",
                        encoding="utf-8")
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_artifact.py -q
```

Ожидание: 9 passed.

- [ ] **Шаг 5: Прогнать полный набор и закоммитить**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **244 passed** (235 + 9).

```bash
git add scripts/factory/artifact.py tests/test_artifact.py
git commit -m "feat(preprod): текстовый артефакт — frontmatter и стабильный хеш тела"
```

---

## Task 2: Состояние артефакта и обнаружение устаревания

Отвечает на вопрос «этот файл всё ещё тот, что одобряли». Две беды ловятся раздельно: правка самого файла (`stale_self`) и уехавшее основание (`stale_deps`).

**Files:**
- Create: `scripts/factory/preprod.py`
- Test: `tests/test_preprod.py`

**Interfaces:**
- Consumes: `factory.artifact.load_artifact`, `Artifact.sha`.
- Produces: `dependencies(project_dir: Path, art: Artifact) -> list[Path]`; `artifact_state(project_dir: Path, path: Path) -> str` со значениями `"missing" | "draft" | "approved" | "stale_self" | "stale_deps"`; константа `DEPENDS_ON: dict[str, list[str]]`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_preprod.py`:

```python
"""Тесты состояния артефактов и гейтов пре-продакшна (спека 2026-08-02 §5)."""
import pytest

from factory.artifact import Artifact, body_sha, load_artifact, save_artifact
from factory.preprod import artifact_state, dependencies


def write(path, kind, body, status="draft", **extra):
    """Записать артефакт; при status='approved' проставить корректные хеши."""
    meta = {"kind": kind, "status": status, **extra}
    if status == "approved":
        meta["content_sha"] = body_sha(body)
    art = Artifact(path=path, meta=meta, body=body)
    save_artifact(art)
    return art


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "bible").mkdir()
    return tmp_path


def test_missing_file(proj):
    assert artifact_state(proj, proj / "bible" / "idea.md") == "missing"


def test_draft(proj):
    write(proj / "bible" / "idea.md", "idea", "идея")
    assert artifact_state(proj, proj / "bible" / "idea.md") == "draft"


def test_approved(proj):
    write(proj / "bible" / "idea.md", "idea", "идея", status="approved")
    assert artifact_state(proj, proj / "bible" / "idea.md") == "approved"


def test_stale_self_when_body_edited_after_approval(proj):
    p = proj / "bible" / "idea.md"
    write(p, "idea", "идея", status="approved")
    art = load_artifact(p)
    art.body = "идея, но переписанная"
    save_artifact(art)
    assert artifact_state(proj, p) == "stale_self"


def test_stale_deps_when_dependency_edited(proj):
    idea = proj / "bible" / "idea.md"
    write(idea, "idea", "идея", status="approved")
    arc = proj / "bible" / "season-arc.md"
    write(arc, "season-arc", "сюжет", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": body_sha("идея")}])
    assert artifact_state(proj, arc) == "approved"

    art = load_artifact(idea)
    art.body = "совсем другая идея"
    save_artifact(art)
    assert artifact_state(proj, arc) == "stale_deps"


def test_stale_deps_when_dependency_deleted(proj):
    arc = proj / "bible" / "season-arc.md"
    write(arc, "season-arc", "сюжет", status="approved",
          depends_on=[{"path": "bible/idea.md", "sha": body_sha("идея")}])
    assert artifact_state(proj, arc) == "stale_deps"


def test_dependencies_of_script(proj):
    art = write(proj / "episodes" / "ep01" / "script.md", "script", "сценарий")
    assert [p.name for p in dependencies(proj, art)] == ["idea.md", "season-arc.md"]


def test_dependencies_of_character_include_scripts_mentioning_it(proj):
    write(proj / "episodes" / "ep01" / "script.md", "script", "Мурзик жмёт кнопку")
    write(proj / "episodes" / "ep02" / "script.md", "script", "Барсик спит")
    art = write(proj / "bible" / "characters" / "Мурзик.md", "character", "рыжий кот")
    got = [p.as_posix().split("projects/")[-1] for p in dependencies(proj, art)]
    assert any("ep01/script.md" in g for g in got)
    assert not any("ep02/script.md" in g for g in got), \
        "Барсик не упомянут — сценарий ep02 не зависимость Мурзика"


def test_dependencies_of_idea_is_empty(proj):
    art = write(proj / "bible" / "idea.md", "idea", "идея")
    assert dependencies(proj, art) == []
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_preprod.py -q
```

Ожидание: FAIL — `ModuleNotFoundError: No module named 'factory.preprod'`.

- [ ] **Шаг 3: Реализовать**

Создать `scripts/factory/preprod.py`:

```python
"""Состояние артефактов и гейты первой половины конвейера (спека 2026-08-02 §5).

Одобрение живёт во frontmatter артефакта вместе с хешом тела и хешами зависимостей,
поэтому правка утверждённого текста не проходит молча.
"""
from __future__ import annotations

from pathlib import Path

from factory.artifact import Artifact, load_artifact

# Карта зависимостей по kind — фиксированная, а не свободный список: иначе два
# запуска approve дали бы разный depends_on и проверка устаревания стала бы
# недетерминированной (спека §4).
DEPENDS_ON: dict[str, list[str]] = {
    "research": [],
    "idea": [],
    "season-arc": ["bible/idea.md"],
    "style-guide": ["bible/idea.md"],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "character": ["bible/idea.md", "bible/style-guide.md"],
}


def dependencies(project_dir: Path, art: Artifact) -> list[Path]:
    """Файлы, от которых артефакт зависит. Для персонажа к статическому списку
    добавляются сценарии, где он упомянут: правка такого сценария меняет то, каким
    персонаж должен быть."""
    project_dir = Path(project_dir)
    kind = art.meta.get("kind")
    deps = [project_dir / rel for rel in DEPENDS_ON.get(kind, [])]
    if kind == "character":
        name = art.meta.get("name") or art.path.stem
        for script in sorted((project_dir / "episodes").glob("*/script.md")):
            if name in load_artifact(script).body:
                deps.append(script)
    return [d for d in deps if d.exists()]


def artifact_state(project_dir: Path, path: Path) -> str:
    """missing | draft | approved | stale_self | stale_deps."""
    project_dir, path = Path(project_dir), Path(path)
    if not path.exists():
        return "missing"
    art = load_artifact(path)
    if art.meta.get("status") != "approved":
        return "draft"
    if art.meta.get("content_sha") != art.sha:
        return "stale_self"
    for dep in art.meta.get("depends_on") or []:
        dep_path = project_dir / dep["path"]
        if not dep_path.exists():
            return "stale_deps"
        if load_artifact(dep_path).sha != dep["sha"]:
            return "stale_deps"
    return "approved"
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_preprod.py -q
```

Ожидание: 9 passed.

- [ ] **Шаг 5: Прогнать полный набор и закоммитить**

Ожидание: **253 passed**.

```bash
git add scripts/factory/preprod.py tests/test_preprod.py
git commit -m "feat(preprod): состояние артефакта и обнаружение устаревания по хешам"
```

---

## Task 3: Гейты этапов и резолвер следующего шага

**Files:**
- Modify: `scripts/factory/preprod.py`
- Test: `tests/test_preprod.py`

**Interfaces:**
- Consumes: `artifact_state`, `factory.project.load_project` (даёт `Project` с полями `type`, `raw`).
- Produces: `STAGES: tuple[str, ...]`; `stage_gate(project_dir: Path, stage: str, episode: str | None = None) -> list[str]`; `next_stage(project_dir: Path) -> tuple[str, str | None] | None`; `episode_ids(project_dir: Path) -> list[str]`.

- [ ] **Шаг 1: Написать падающий тест**

Дописать в `tests/test_preprod.py`:

```python
import json

from factory.preprod import episode_ids, next_stage, stage_gate


def make_project(tmp_path, episodes=2):
    (tmp_path / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": episodes, "episode_duration_sec": 10,
    }), encoding="utf-8")
    return tmp_path


def test_episode_ids_from_project(tmp_path):
    p = make_project(tmp_path, episodes=3)
    assert episode_ids(p) == ["ep01", "ep02", "ep03"]


def test_story_gate_open_on_fresh_project(tmp_path):
    p = make_project(tmp_path)
    assert stage_gate(p, "story") == []


def test_script_gate_blocked_without_approved_story(tmp_path):
    p = make_project(tmp_path)
    problems = stage_gate(p, "script", "ep01")
    assert len(problems) == 2
    assert all("idea.md" in x or "season-arc.md" in x for x in problems)


def test_script_gate_open_after_story_approved(tmp_path):
    p = make_project(tmp_path)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    assert stage_gate(p, "script", "ep01") == []


def test_characters_gate_requires_approved_script(tmp_path):
    p = make_project(tmp_path)
    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    assert stage_gate(p, "characters", "ep01") != []
    write(p / "episodes" / "ep01" / "script.md", "script", "текст", status="approved")
    assert stage_gate(p, "characters", "ep01") == []


def test_gate_reports_stale_differently_from_draft(tmp_path):
    p = make_project(tmp_path)
    idea = p / "bible" / "idea.md"
    write(idea, "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    art = load_artifact(idea)
    art.body = "переписал"
    save_artifact(art)
    problems = stage_gate(p, "script", "ep01")
    assert any("изменён после одобрения" in x for x in problems)


def test_next_stage_walks_all_episodes_in_order(tmp_path):
    p = make_project(tmp_path, episodes=2)
    assert next_stage(p) == ("story", None)

    write(p / "bible" / "idea.md", "idea", "идея", status="approved")
    write(p / "bible" / "season-arc.md", "season-arc", "арка", status="approved")
    write(p / "bible" / "style-guide.md", "style-guide", "стиль", status="approved")
    assert next_stage(p) == ("script", "ep01")

    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    assert next_stage(p) == ("characters", "ep01")


def test_next_stage_none_when_nothing_left(tmp_path):
    p = make_project(tmp_path, episodes=1)
    for rel, kind in (("bible/idea.md", "idea"), ("bible/season-arc.md", "season-arc"),
                      ("bible/style-guide.md", "style-guide")):
        write(p / rel, kind, "текст", status="approved")
    write(p / "episodes" / "ep01" / "script.md", "script", "с1", status="approved")
    write(p / "bible" / "characters" / "Мурзик.md", "character", "кот", status="approved")
    (p / "episodes" / "ep01" / "shots.json").write_text("{}", encoding="utf-8")
    assert next_stage(p) is None
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_preprod.py -k "gate or next_stage or episode_ids" -q
```

Ожидание: FAIL — `ImportError: cannot import name 'stage_gate'`.

- [ ] **Шаг 3: Реализовать**

Дописать в `scripts/factory/preprod.py`:

```python
import json

STAGES = ("research", "story", "script", "characters", "storyboard")

# Что каждый этап требует одобренным. {ep} подставляется номером эпизода.
STAGE_REQUIRES: dict[str, list[str]] = {
    "research": [],
    "story": [],
    "script": ["bible/idea.md", "bible/season-arc.md"],
    "characters": ["episodes/{ep}/script.md"],
    "storyboard": ["episodes/{ep}/script.md", "bible/style-guide.md"],
}

_STATE_MESSAGE = {
    "missing": "не существует",
    "draft": "не одобрен (status: draft)",
    "stale_self": "изменён после одобрения — перечитай и одобри заново",
    "stale_deps": "устарел: изменился файл, на который он опирался",
}


def episode_ids(project_dir: Path) -> list[str]:
    """ep01..epNN по полю episodes из project.json; для типов без серий — ['ep01']."""
    data = json.loads((Path(project_dir) / "project.json").read_text(encoding="utf-8"))
    count = int(data.get("episodes", 1) or 1)
    return [f"ep{i:02d}" for i in range(1, count + 1)]


def stage_gate(project_dir: Path, stage: str, episode: str | None = None) -> list[str]:
    """Пустой список = этап можно запускать. Иначе — по строке на каждую причину."""
    project_dir = Path(project_dir)
    if stage not in STAGES:
        return [f"неизвестный этап {stage!r}; известны {list(STAGES)}"]

    problems: list[str] = []
    for template in STAGE_REQUIRES[stage]:
        if "{ep}" in template and episode is None:
            problems.append(f"этап {stage} требует --episode")
            continue
        rel = template.format(ep=episode)
        state = artifact_state(project_dir, project_dir / rel)
        if state != "approved":
            problems.append(f"{rel}: {_STATE_MESSAGE[state]}")

    if stage == "storyboard":
        chars = sorted((project_dir / "bible" / "characters").glob("*.md"))
        if not chars:
            problems.append("bible/characters/: нет ни одной карточки персонажа")
        for card in chars:
            state = artifact_state(project_dir, card)
            if state != "approved":
                rel = card.relative_to(project_dir).as_posix()
                problems.append(f"{rel}: {_STATE_MESSAGE[state]}")
    return problems


def next_stage(project_dir: Path) -> tuple[str, str | None] | None:
    """Первый незакрытый шаг. Порядок: story, затем эпизоды ПО ПОРЯДКУ, в каждом
    script → characters → storyboard (спека §7: автономный режим идёт по всем)."""
    project_dir = Path(project_dir)
    story_done = all(
        artifact_state(project_dir, project_dir / rel) == "approved"
        for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"))
    if not story_done:
        return ("story", None)

    for ep in episode_ids(project_dir):
        if artifact_state(project_dir, project_dir / f"episodes/{ep}/script.md") != "approved":
            return ("script", ep)
        chars = sorted((project_dir / "bible" / "characters").glob("*.md"))
        if not chars or any(artifact_state(project_dir, c) != "approved" for c in chars):
            return ("characters", ep)
        if not (project_dir / "episodes" / ep / "shots.json").exists():
            return ("storyboard", ep)
    return None
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_preprod.py -q
```

Ожидание: 17 passed.

- [ ] **Шаг 5: Прогнать полный набор и закоммитить**

Ожидание: **261 passed**.

```bash
git add scripts/factory/preprod.py tests/test_preprod.py
git commit -m "feat(preprod): гейты этапов и резолвер следующего шага по всем эпизодам"
```

---

## Task 4: CLI `factory.py` — init, status, check, approve, next

`approve` — единственное место, где появляется `status: approved`: одобрение это действие человека, и след о нём должен остаться в файле, а не в диалоге.

**Files:**
- Create: `scripts/factory.py`
- Test: `tests/test_factory_cli.py`

**Interfaces:**
- Consumes: `factory.preprod.{artifact_state, stage_gate, next_stage, episode_ids, dependencies}`, `factory.artifact.{load_artifact, save_artifact, Artifact}`.
- Produces: CLI. Коды возврата: 0 успех; 1 ошибка данных; 3 гейт закрыт.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_factory_cli.py`:

```python
"""Тесты CLI пре-продакшна (спека 2026-08-02 §6)."""
import json

import pytest

import factory_cli_entry as fc  # см. шаг 3: тонкая обёртка над scripts/factory.py
from factory.artifact import load_artifact
from factory.preprod import artifact_state


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / "projects" / "pilot").mkdir(parents=True)
    (tmp_path / "projects" / "pilot" / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 2, "episode_duration_sec": 10,
    }), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path / "projects" / "pilot"


def run(*args):
    return fc.main([str(a) for a in args])


def test_init_creates_tree_with_drafts(proj):
    assert run("init", "--project", proj) == 0
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"):
        assert artifact_state(proj, proj / rel) == "draft"


def test_init_is_idempotent_and_keeps_content(proj):
    run("init", "--project", proj)
    art = load_artifact(proj / "bible" / "idea.md")
    art.body = "уже написанная идея"
    from factory.artifact import save_artifact
    save_artifact(art)

    assert run("init", "--project", proj) == 0
    assert "уже написанная идея" in load_artifact(proj / "bible" / "idea.md").body


def test_check_returns_3_when_gate_closed(proj):
    run("init", "--project", proj)
    assert run("check", "--project", proj, "--stage", "script", "--episode", "ep01") == 3


def test_approve_sets_status_and_hashes(proj):
    run("init", "--project", proj)
    art = load_artifact(proj / "bible" / "idea.md")
    art.body = "идея"
    from factory.artifact import save_artifact
    save_artifact(art)

    assert run("approve", "--project", proj, "bible/idea.md") == 0
    saved = load_artifact(proj / "bible" / "idea.md")
    assert saved.meta["status"] == "approved"
    assert saved.meta["content_sha"] == saved.sha
    assert "approved_at" in saved.meta


def test_approve_records_dependency_hashes(proj):
    run("init", "--project", proj)
    run("approve", "--project", proj, "bible/idea.md")
    assert run("approve", "--project", proj, "bible/season-arc.md") == 0
    arc = load_artifact(proj / "bible" / "season-arc.md")
    deps = {d["path"]: d["sha"] for d in arc.meta["depends_on"]}
    assert deps["bible/idea.md"] == load_artifact(proj / "bible" / "idea.md").sha


def test_approve_refuses_missing_file(proj):
    run("init", "--project", proj)
    assert run("approve", "--project", proj, "bible/nope.md") == 1


def test_check_opens_after_approve(proj):
    run("init", "--project", proj)
    run("approve", "--project", proj, "bible/idea.md")
    run("approve", "--project", proj, "bible/season-arc.md")
    assert run("check", "--project", proj, "--stage", "script", "--episode", "ep01") == 0


def test_next_prints_story_first(proj, capsys):
    run("init", "--project", proj)
    assert run("next", "--project", proj) == 0
    assert "story" in capsys.readouterr().out


def test_status_lists_every_artifact(proj, capsys):
    run("init", "--project", proj)
    run("status", "--project", proj)
    out = capsys.readouterr().out
    for rel in ("bible/idea.md", "bible/season-arc.md", "bible/style-guide.md"):
        assert rel in out
```

- [ ] **Шаг 2: Дать тесту импортируемое имя**

`scripts/factory.py` нельзя импортировать как `factory` — это имя занято пакетом `scripts/factory/`. Поэтому CLI живёт в `scripts/factory.py`, а тест импортирует его через явную загрузку. Создать `tests/factory_cli_entry.py`:

```python
"""Импорт scripts/factory.py под именем, не конфликтующим с пакетом factory."""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "scripts" / "factory.py"
_spec = importlib.util.spec_from_file_location("factory_cli", _path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main
```

- [ ] **Шаг 3: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_factory_cli.py -q
```

Ожидание: FAIL — `FileNotFoundError` на `scripts/factory.py`.

- [ ] **Шаг 4: Реализовать**

Создать `scripts/factory.py`:

```python
"""CLI пре-продакшна: состояние проекта, гейты, одобрения (спека 2026-08-02 §6).

Запускать из корня репозитория:
  python scripts/factory.py status  --project projects/pilot
  python scripts/factory.py next    --project projects/pilot
  python scripts/factory.py check   --project projects/pilot --stage script --episode ep01
  python scripts/factory.py approve --project projects/pilot bible/idea.md

Коды выхода: 0 успех; 1 ошибка данных; 3 гейт закрыт.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.artifact import Artifact, load_artifact, save_artifact
from factory.preprod import (artifact_state, dependencies, episode_ids,
                             next_stage, stage_gate)

# Артефакты, которые создаёт init. Персонажи не скаффолдятся: их состав известен
# только после сценария.
SCAFFOLD = {
    "bible/idea.md": "idea",
    "bible/season-arc.md": "season-arc",
    "bible/style-guide.md": "style-guide",
}


def _project_artifacts(project_dir: Path) -> list[Path]:
    paths = [project_dir / rel for rel in SCAFFOLD]
    paths += sorted((project_dir / "bible" / "characters").glob("*.md"))
    paths += sorted((project_dir / "episodes").glob("*/script.md"))
    research = project_dir / "research.md"
    if research.exists():
        paths.append(research)
    return paths


def cmd_init(project_dir: Path) -> int:
    for rel, kind in SCAFFOLD.items():
        path = project_dir / rel
        if path.exists():
            continue          # идемпотентность: написанное не затираем
        save_artifact(Artifact(path=path, meta={"kind": kind, "status": "draft"},
                               body=""))
        print(f"создан {rel}")
    for ep in episode_ids(project_dir):
        (project_dir / "episodes" / ep).mkdir(parents=True, exist_ok=True)
    return 0


def cmd_status(project_dir: Path) -> int:
    for path in _project_artifacts(project_dir):
        rel = path.relative_to(project_dir).as_posix()
        print(f"{rel:34} {artifact_state(project_dir, path)}")
    return 0


def cmd_next(project_dir: Path) -> int:
    nxt = next_stage(project_dir)
    if nxt is None:
        print("всё закрыто — следующего шага нет")
        return 0
    stage, episode = nxt
    print(f"{stage} {episode or ''}".strip())
    return 0


def cmd_check(project_dir: Path, stage: str, episode: str | None) -> int:
    problems = stage_gate(project_dir, stage, episode)
    if not problems:
        print(f"гейт открыт: {stage} {episode or ''}".strip())
        return 0
    print(f"ГЕЙТ ЗАКРЫТ — этап {stage} запускать нельзя:")
    for p in problems:
        print(f"  - {p}")
    return 3


def cmd_approve(project_dir: Path, rel: str) -> int:
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    art = load_artifact(path)
    if not art.body.strip():
        print(f"{rel}: тело пустое — нечего одобрять")
        return 1
    art.meta["status"] = "approved"
    art.meta["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds")
    art.meta["content_sha"] = art.sha
    deps = []
    for dep in dependencies(project_dir, art):
        deps.append({"path": dep.relative_to(project_dir).as_posix(),
                     "sha": load_artifact(dep).sha})
    if deps:
        art.meta["depends_on"] = deps
    save_artifact(art)
    print(f"одобрено: {rel}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "status", "next"):
        sub.add_parser(name).add_argument("--project", required=True)
    check = sub.add_parser("check")
    check.add_argument("--project", required=True)
    check.add_argument("--stage", required=True)
    check.add_argument("--episode")
    approve = sub.add_parser("approve")
    approve.add_argument("--project", required=True)
    approve.add_argument("artifact")

    args = ap.parse_args(argv)
    project_dir = Path(args.project)
    if not (project_dir / "project.json").exists():
        print(f"нет {project_dir / 'project.json'}")
        return 1

    if args.cmd == "init":
        return cmd_init(project_dir)
    if args.cmd == "status":
        return cmd_status(project_dir)
    if args.cmd == "next":
        return cmd_next(project_dir)
    if args.cmd == "check":
        return cmd_check(project_dir, args.stage, args.episode)
    return cmd_approve(project_dir, args.artifact)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_factory_cli.py -q
```

Ожидание: 9 passed.

- [ ] **Шаг 6: Прогнать полный набор и закоммитить**

Ожидание: **270 passed**.

```bash
git add scripts/factory.py tests/test_factory_cli.py tests/factory_cli_entry.py
git commit -m "feat(preprod): CLI factory.py — init, status, check, approve, next"
```

---

## Task 5: Плейсхолдеры в промптах и их разворачивание

Дословная вставка канонических блоков в каждый из ~60 промптов серии стоит тысяч токенов дублированного текста и даёт шанс незаметно перефразировать блок. `shots.json` хранит плейсхолдеры, разворачивает код перед сабмитом.

**Files:**
- Create: `scripts/factory/prompts.py`
- Modify: `scripts/generate_batch.py`
- Test: `tests/test_prompts.py`, `tests/test_generate_batch.py`

**Interfaces:**
- Consumes: `factory.artifact.load_artifact`.
- Produces: `canonical_block(path: Path, name: str) -> str`; `expand_prompt(prompt: str, project_dir: Path) -> str`; `prompt_problems(prompt: str, project_dir: Path, refs: list[str]) -> list[str]`; `PromptError(ValueError)`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `tests/test_prompts.py`:

```python
"""Тесты плейсхолдеров в промптах кадров (спека 2026-08-02 §10)."""
import pytest

from factory.artifact import Artifact, save_artifact
from factory.prompts import PromptError, canonical_block, expand_prompt, prompt_problems

STYLE = """Общий стиль сериала.

<!-- canonical:style -->
flat 2D cartoon, thick outlines, saturated palette
<!-- /canonical:style -->
"""

MURZIK = """Рыжий кот-астронавт.

<!-- canonical:appearance -->
orange tabby cat, white chest patch, blue spacesuit
<!-- /canonical:appearance -->
"""


@pytest.fixture
def proj(tmp_path):
    save_artifact(Artifact(path=tmp_path / "bible" / "style-guide.md",
                           meta={"kind": "style-guide", "status": "approved"},
                           body=STYLE))
    save_artifact(Artifact(path=tmp_path / "bible" / "characters" / "murzik.md",
                           meta={"kind": "character", "status": "approved"},
                           body=MURZIK))
    return tmp_path


def test_canonical_block_extracted(proj):
    got = canonical_block(proj / "bible" / "style-guide.md", "style")
    assert got == "flat 2D cartoon, thick outlines, saturated palette"


def test_canonical_block_missing_raises(proj):
    with pytest.raises(PromptError, match="canonical:appearance"):
        canonical_block(proj / "bible" / "style-guide.md", "appearance")


def test_expand_substitutes_style_and_character(proj):
    got = expand_prompt("{{style}} {{char:murzik}} presses a button", proj)
    assert "flat 2D cartoon" in got
    assert "orange tabby cat" in got
    assert "{{" not in got


def test_expand_unknown_character_raises(proj):
    with pytest.raises(PromptError, match="barsik"):
        expand_prompt("{{char:barsik}} sleeps", proj)


def test_expand_unknown_placeholder_raises(proj):
    with pytest.raises(PromptError, match="mood"):
        expand_prompt("{{mood}} scene", proj)


def test_problems_flags_missing_style(proj):
    problems = prompt_problems("{{char:murzik}} sits", proj, [])
    assert any("{{style}}" in p for p in problems)


def test_problems_flags_character_without_ref(proj):
    problems = prompt_problems("{{style}} {{char:murzik}} sits", proj, [])
    assert any("murzik" in p and "refs" in p for p in problems)


def test_problems_empty_when_everything_declared(proj):
    refs = ["bible/characters/murzik-ref.png"]
    assert prompt_problems("{{style}} {{char:murzik}} sits", proj, refs) == []


def test_problems_flags_unapproved_character(proj):
    card = proj / "bible" / "characters" / "murzik.md"
    save_artifact(Artifact(path=card, meta={"kind": "character", "status": "draft"},
                           body=MURZIK))
    problems = prompt_problems("{{style}} {{char:murzik}} sits", proj,
                               ["bible/characters/murzik-ref.png"])
    assert any("не одобрен" in p for p in problems)
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -q
```

Ожидание: FAIL — `ModuleNotFoundError: No module named 'factory.prompts'`.

- [ ] **Шаг 3: Реализовать**

Создать `scripts/factory/prompts.py`:

```python
"""Плейсхолдеры в промптах кадров и их разворачивание (спека 2026-08-02 §10).

Промпт уходит по HTTP внешней модели — у неё нет файловой системы, поэтому
канонические блоки обязаны попасть в текст дословно. Плейсхолдер даёт дословность
кодом, а не дисциплиной: перефразировать при копировании физически некому.
"""
from __future__ import annotations

import re
from pathlib import Path

from factory.artifact import load_artifact

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)(?:\s*:\s*([\w\-]+))?\s*\}\}")


class PromptError(ValueError):
    pass


def _canonical_re(name: str) -> re.Pattern:
    return re.compile(rf"<!--\s*canonical:{name}\s*-->(.*?)<!--\s*/canonical:{name}\s*-->",
                      re.DOTALL)


def canonical_block(path: Path, name: str) -> str:
    """Текст между маркерами <!-- canonical:<name> --> и закрывающим."""
    path = Path(path)
    if not path.exists():
        raise PromptError(f"{path}: файл не найден")
    match = _canonical_re(name).search(load_artifact(path).body)
    if not match:
        raise PromptError(f"{path}: нет блока canonical:{name}")
    return match.group(1).strip()


def _character_card(project_dir: Path, name: str) -> Path:
    return Path(project_dir) / "bible" / "characters" / f"{name}.md"


def expand_prompt(prompt: str, project_dir: Path) -> str:
    """Подставить канонические блоки вместо плейсхолдеров. Неизвестный плейсхолдер —
    ошибка, а не молчаливый пропуск: иначе провайдер получит текст с '{{...}}'."""
    project_dir = Path(project_dir)

    def replace(m: re.Match) -> str:
        kind, arg = m.group(1), m.group(2)
        if kind == "style" and arg is None:
            return canonical_block(project_dir / "bible" / "style-guide.md", "style")
        if kind == "char" and arg:
            card = _character_card(project_dir, arg)
            if not card.exists():
                raise PromptError(f"нет карточки персонажа {arg!r} ({card})")
            return canonical_block(card, "appearance")
        raise PromptError(f"неизвестный плейсхолдер {m.group(0)!r}")

    return _PLACEHOLDER.sub(replace, prompt)


def prompt_problems(prompt: str, project_dir: Path, refs: list[str]) -> list[str]:
    """Проверки гейта раскадровки. Пустой список = промпт годен."""
    project_dir = Path(project_dir)
    problems: list[str] = []
    found = _PLACEHOLDER.findall(prompt)

    if not any(kind == "style" for kind, _ in found):
        problems.append("в промпте нет {{style}}")

    refs_joined = " ".join(refs)
    for kind, arg in found:
        if kind == "style":
            continue
        if kind != "char" or not arg:
            problems.append(f"неизвестный плейсхолдер {{{{{kind}}}}}")
            continue
        card = _character_card(project_dir, arg)
        if not card.exists():
            problems.append(f"персонаж {arg!r}: нет карточки {card.name}")
            continue
        if load_artifact(card).meta.get("status") != "approved":
            problems.append(f"персонаж {arg!r}: не одобрен")
        if f"{arg}-ref" not in refs_joined:
            problems.append(f"персонаж {arg!r}: нет его референса в refs кадра")
    return problems
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -q
```

Ожидание: 9 passed.

- [ ] **Шаг 5: Подключить разворачивание в конвейер**

В `scripts/generate_batch.py` добавить импорт рядом с остальными `factory`-импортами:

```python
from factory.prompts import expand_prompt
```

В `build_jobs`, в ветке `storyboard`, заменить формирование `params` так, чтобы промпт разворачивался, а развёрнутый текст был виден в манифесте:

```python
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
```

И в цикле генерации, в вызове `manifest.set_status(... "generated" ...)`, добавить поле с фактически отправленным промптом:

```python
            manifest.set_status(
                j["item_id"], "generated", file=str(j["dest"]), job_id=job_id,
                prompt_sent=j["params"].get("prompt"),
                credits_spent=item["credits_spent"] + estimates[j["item_id"]])
```

- [ ] **Шаг 6: Подключить проверки промптов как гейт трат**

Проверки бесполезны, пока их никто не зовёт. `generate_batch` в ветке `storyboard`
обязан отбить негодные промпты **до сметы**, иначе кадр без референса персонажа
оплатится и придёт неконсистентным.

В `scripts/generate_batch.py` добавить импорт `prompt_problems` рядом с `expand_prompt`
и вставить в ветку `else:` (storyboard) сразу после проверки принятых референсов:

```python
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
```

Код 2, а не 3: это негодные данные того же класса, что непрошедшая валидацию модель,
а не незакрытый предыдущий шаг.

- [ ] **Шаг 7: Добавить тесты интеграции**

В `tests/test_generate_batch.py` дописать:

```python
def test_storyboard_rejects_frame_without_style_placeholder(proj, monkeypatch):
    """Кадр без {{style}} — потеря стиля на всю серию; отбиваем до трат."""
    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    shots["frames"][0]["prompt"] = "cat on a fence"
    (proj / "episodes" / "ep01" / "shots.json").write_text(json.dumps(shots),
                                                           encoding="utf-8")
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 2
    assert fp.submitted == [], "до провайдера дойти не должно"


def test_storyboard_expands_placeholders_and_records_sent_prompt(proj, monkeypatch):
    """Провайдер получает развёрнутый текст, а манифест хранит то, что реально ушло."""
    from factory.artifact import Artifact, save_artifact
    save_artifact(Artifact(
        path=proj / "bible" / "style-guide.md",
        meta={"kind": "style-guide", "status": "approved"},
        body="<!-- canonical:style -->flat 2D cartoon<!-- /canonical:style -->"))

    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    shots["frames"][0]["prompt"] = "{{style}} cat on a fence"
    (proj / "episodes" / "ep01" / "shots.json").write_text(json.dumps(shots),
                                                           encoding="utf-8")

    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp.submitted[0]["prompt"] == "flat 2D cartoon cat on a fence"

    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["prompt_sent"] == "flat 2D cartoon cat on a fence"
```

- [ ] **Шаг 7: Прогнать полный набор и закоммитить**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **281 passed**.

```bash
git add scripts/factory/prompts.py scripts/generate_batch.py tests/test_prompts.py tests/test_generate_batch.py
git commit -m "feat(preprod): плейсхолдеры в промптах кадров и их разворачивание перед сабмитом"
```

---

## Task 6: Стадия `characters` в generate_batch

Референс-лист персонажа — обычная платная генерация картинки, поэтому идёт через уже готовое: манифест, гейт трат, `review.py`.

**Files:**
- Modify: `scripts/generate_batch.py`
- Test: `tests/test_generate_batch.py`

**Interfaces:**
- Consumes: `factory.preprod.stage_gate`, `factory.prompts.canonical_block`.
- Produces: `--stage characters`; item в манифесте с `kind="character_ref"` и id `bible/characters/<name>`; файл `bible/characters/<name>-ref.png`.

- [ ] **Шаг 1: Написать падающий тест**

В `tests/test_generate_batch.py` дописать:

```python
def _character_card(proj, name, status="approved"):
    from factory.artifact import Artifact, save_artifact
    save_artifact(Artifact(
        path=proj / "bible" / "characters" / f"{name}.md",
        meta={"kind": "character", "status": status},
        body=f"<!-- canonical:appearance -->orange cat {name}<!-- /canonical:appearance -->"))


def test_characters_stage_generates_one_ref_per_card(proj, monkeypatch):
    _character_card(proj, "murzik")
    _character_card(proj, "barsik")
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 0
    assert len(fp.submitted) == 2
    m = Manifest(proj / "manifest.json")
    assert m.get("bible/characters/murzik")["kind"] == "character_ref"
    assert (proj / "bible" / "characters" / "murzik-ref.png").exists()


def test_characters_stage_prompt_contains_appearance(proj, monkeypatch):
    _character_card(proj, "murzik")
    fp = fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    assert "orange cat murzik" in fp.submitted[0]["prompt"]


def test_characters_stage_blocked_without_cards(proj, monkeypatch):
    fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 3


def test_storyboard_blocked_until_character_refs_accepted(proj, monkeypatch):
    """Кадры нельзя генерировать, пока референс персонажа не принят ревью."""
    _character_card(proj, "murzik")
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01", "--stage", "characters", "--yes"])
    # референс сгенерирован, но не принят
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "storyboard", "--yes"]) == 3
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -k characters -q
```

Ожидание: FAIL — `argparse` отвергает `--stage characters` (`invalid choice`).

- [ ] **Шаг 3: Реализовать**

В `scripts/generate_batch.py`:

1. Расширить выбор стадий:

```python
    ap.add_argument("--stage", required=True,
                    choices=["storyboard", "segments", "characters"])
```

2. Добавить импорты:

```python
from factory.prompts import canonical_block, expand_prompt
```

3. В `build_jobs` добавить ветку до `if stage == "storyboard":`:

```python
    if stage == "characters":
        cards = sorted((project_dir / "bible" / "characters").glob("*.md"))
        for card in cards:
            name = card.stem
            appearance = canonical_block(card, "appearance")
            jobs.append({
                "item_id": f"bible/characters/{name}",
                "kind": "character_ref",
                "model": project.image_model,
                "dest": card.with_name(f"{name}-ref.png"),
                "params": {
                    "prompt": f"character sheet, three angles, neutral background. "
                              f"{appearance}",
                    "refs": [], "aspect_ratio": aspect,
                    "resolution": project.resolution, "tier": project.image_tier,
                },
            })
        return jobs
```

4. В `main`, в ветке выбора провайдера, обрабатывать `characters` как image-стадию и добавить гейт на наличие одобренных карточек. Заменить `else:` (ветку storyboard) на:

```python
    else:
        provider_name = project.image_provider
        if args.stage == "characters":
            # Гейт первой половины: генерировать референсы не по чему, если карточек
            # нет или они не одобрены (спека пре-продакшна §5).
            problems = stage_gate(project_dir, "characters", args.episode)
            cards = sorted((project_dir / "bible" / "characters").glob("*.md"))
            if not cards:
                problems.append("bible/characters/: нет ни одной карточки персонажа")
            if problems:
                print("ГЕЙТ ЗАКРЫТ — стадия characters недоступна:")
                for p in problems:
                    print(f"  - {p}")
                return 3
        # Гейт трат раскадровки (симметрично video): валидация image-модели под
        # выбранного провайдера ДО сметы — skeleton/не-тот-провайдер → код 2.
        card = find_card(KNOWLEDGE_DIR, project.image_model)
        problems = validate_image_model(card, provider_name)
        if problems:
            return _validation_gate(problems)
```

и добавить импорт `stage_gate`:

```python
from factory.preprod import stage_gate
```

5. В ветке `storyboard` добавить проверку принятых референсов — сразу после существующего чекпоинта кадров вставить (внутри `if args.stage == "segments":` ничего не менять; это отдельный блок в ветке `else`, до валидации модели):

```python
        if args.stage == "storyboard":
            accepted = {"done", "accepted_with_notes"}
            not_ready = []
            for card in sorted((project_dir / "bible" / "characters").glob("*.md")):
                item_id = f"bible/characters/{card.stem}"
                try:
                    status = manifest.get(item_id)["status"]
                except ManifestError:
                    not_ready.append(f"{item_id}: референс не генерировался")
                    continue
                if status not in accepted:
                    not_ready.append(f"{item_id}: статус {status}")
            if not_ready:
                print("РЕФЕРЕНСЫ ПЕРСОНАЖЕЙ НЕ ПРИНЯТЫ — стадия storyboard заблокирована:")
                for p in not_ready:
                    print(f"  - {p}")
                return 3
```

6. Обновить докстроку модуля: добавить `characters` в перечень стадий и в описание кодов выхода упомянуть, что 3 отдаётся также при закрытом гейте пре-продакшна.

- [ ] **Шаг 4: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_generate_batch.py -q
```

Ожидание: все тесты файла зелёные.

- [ ] **Шаг 5: Прогнать полный набор и закоммитить**

Ожидание: **285 passed**.

```bash
git add scripts/generate_batch.py tests/test_generate_batch.py
git commit -m "feat(preprod): стадия characters — референсы персонажей через манифест и ревью"
```

---

## Task 7: Петля обратной связи — поле feedback, diff, колонка в status

Молчание пользователя двусмысленно: он мог одобрить, а мог не дойти. `none` означает «неизвестно», а не «хорошо».

**Files:**
- Modify: `scripts/factory.py`, `scripts/factory/preprod.py`
- Test: `tests/test_factory_cli.py`

**Interfaces:**
- Produces: `factory.preprod.feedback_state(path) -> str` (`"none" | "pending" | "recorded"`); подкоманды `factory.py diff` и `factory.py feedback set`.

- [ ] **Шаг 1: Написать падающий тест**

В `tests/test_factory_cli.py` дописать:

```python
def test_feedback_defaults_to_none(proj):
    run("init", "--project", proj)
    from factory.preprod import feedback_state
    assert feedback_state(proj / "bible" / "idea.md") == "none"


def test_status_shows_feedback_column(proj, capsys):
    run("init", "--project", proj)
    run("status", "--project", proj)
    out = capsys.readouterr().out
    assert "feedback" in out
    assert "none" in out


def test_feedback_set_records_state(proj):
    run("init", "--project", proj)
    assert run("feedback", "--project", proj, "bible/idea.md", "--state", "recorded") == 0
    from factory.preprod import feedback_state
    assert feedback_state(proj / "bible" / "idea.md") == "recorded"


def test_feedback_rejects_unknown_state(proj):
    run("init", "--project", proj)
    assert run("feedback", "--project", proj, "bible/idea.md", "--state", "great") == 1


def test_diff_reports_no_baseline_when_never_committed(proj, capsys):
    run("init", "--project", proj)
    assert run("diff", "--project", proj, "bible/idea.md") == 0
    assert "нет базовой версии" in capsys.readouterr().out
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_factory_cli.py -k feedback -q
```

Ожидание: FAIL — `ImportError: cannot import name 'feedback_state'`.

- [ ] **Шаг 3: Реализовать**

В `scripts/factory/preprod.py` дописать:

```python
FEEDBACK_STATES = ("none", "pending", "recorded")


def feedback_state(path: Path) -> str:
    """none — оценки не было и правок не было; это «неизвестно», а не «хорошо».
    pending — человек правил, причина не разобрана. recorded — правило записано
    в bible/craft-notes.md (спека §11)."""
    path = Path(path)
    if not path.exists():
        return "none"
    value = load_artifact(path).meta.get("feedback", "none")
    return value if value in FEEDBACK_STATES else "none"
```

В `scripts/factory.py`:

1. Импорт: `from factory.preprod import ..., feedback_state, FEEDBACK_STATES` и `import subprocess`.

2. Заменить `cmd_status` на версию с колонкой:

```python
def cmd_status(project_dir: Path) -> int:
    print(f"{'артефакт':34} {'состояние':12} feedback")
    for path in _project_artifacts(project_dir):
        rel = path.relative_to(project_dir).as_posix()
        print(f"{rel:34} {artifact_state(project_dir, path):12} "
              f"{feedback_state(path)}")
    return 0
```

3. Добавить команды:

```python
def cmd_feedback(project_dir: Path, rel: str, state: str) -> int:
    if state not in FEEDBACK_STATES:
        print(f"неизвестное состояние {state!r}; известны {list(FEEDBACK_STATES)}")
        return 1
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    art = load_artifact(path)
    art.meta["feedback"] = state
    save_artifact(art)
    print(f"{rel}: feedback={state}")
    return 0


def cmd_diff(project_dir: Path, rel: str) -> int:
    """Что человек изменил с момента генерации. Базовая версия — последний коммит
    файла: скилл коммитит артефакт сразу после записи (спека §11)."""
    path = project_dir / rel
    if not path.exists():
        print(f"нет файла {rel}")
        return 1
    result = subprocess.run(["git", "log", "-1", "--format=%H", "--", str(path)],
                            capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not result.stdout.strip():
        print(f"{rel}: нет базовой версии в git — сравнивать не с чем")
        return 0
    diff = subprocess.run(["git", "diff", "HEAD", "--", str(path)],
                          capture_output=True, encoding="utf-8", errors="replace")
    print(diff.stdout or f"{rel}: правок с момента коммита нет")
    return 0
```

4. Зарегистрировать в `main`:

```python
    fb = sub.add_parser("feedback")
    fb.add_argument("--project", required=True)
    fb.add_argument("artifact")
    fb.add_argument("--state", required=True)
    df = sub.add_parser("diff")
    df.add_argument("--project", required=True)
    df.add_argument("artifact")
```

и в диспетчере, до `return cmd_approve(...)`:

```python
    if args.cmd == "feedback":
        return cmd_feedback(project_dir, args.artifact, args.state)
    if args.cmd == "diff":
        return cmd_diff(project_dir, args.artifact)
```

- [ ] **Шаг 4: Добавить потолок бюджета для автономного режима**

Режим `autonomy: full` тратит без вопросов, и единственное, что его удерживает —
`budget_usd`. Оставлять этот потолок дисциплиной скилла нельзя: вся спека построена на
том, что гейты проверяет код. Нужна команда, которую драйвер обязан спросить перед
платной стадией.

Тест в `tests/test_factory_cli.py`:

```python
def test_budget_allows_estimate_within_remainder(proj):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "autonomy": "full", "budget_usd": 10,
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "3.0") == 0


def test_budget_blocks_estimate_over_remainder(proj, capsys):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "autonomy": "full", "budget_usd": 1,
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "3.0") == 3
    assert "бюджет" in capsys.readouterr().out


def test_budget_counts_already_spent(proj):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10,
        "autonomy": "full", "budget_usd": 5,
    }), encoding="utf-8")
    from factory.manifest import Manifest
    m = Manifest(proj / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generated", credits_spent=4.5)
    m.save()
    assert run("budget", "--project", proj, "--estimate", "1.0") == 3


def test_budget_requires_budget_usd_in_full_mode(proj, capsys):
    (proj / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "t", "audience": "6-9",
        "episodes": 1, "episode_duration_sec": 10, "autonomy": "full",
    }), encoding="utf-8")
    assert run("budget", "--project", proj, "--estimate", "0.1") == 1
    assert "budget_usd" in capsys.readouterr().out
```

Реализация в `scripts/factory.py` (импорт `from factory.manifest import Manifest`):

```python
def cmd_budget(project_dir: Path, estimate: float) -> int:
    """Влезает ли смета в остаток budget_usd. Только для autonomy: full — в
    остальных режимах трату подтверждает человек, потолок не нужен."""
    data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    if data.get("autonomy") != "full":
        print("режим не full — потолок бюджета не применяется")
        return 0
    budget = data.get("budget_usd")
    if budget is None:
        print("autonomy: full требует budget_usd в project.json")
        return 1
    manifest_path = project_dir / "manifest.json"
    spent = Manifest(manifest_path).credits_total() if manifest_path.exists() else 0.0
    remainder = float(budget) - spent
    if estimate > remainder:
        print(f"БЮДЖЕТ ИСЧЕРПАН: смета ${estimate:.4f} > остаток ${remainder:.4f} "
              f"(потолок ${float(budget):.2f}, потрачено ${spent:.4f})")
        return 3
    print(f"в бюджете: смета ${estimate:.4f}, остаток ${remainder:.4f}")
    return 0
```

Зарегистрировать (нужен `import json` в начале файла):

```python
    bg = sub.add_parser("budget")
    bg.add_argument("--project", required=True)
    bg.add_argument("--estimate", type=float, required=True)
```

и в диспетчере:

```python
    if args.cmd == "budget":
        return cmd_budget(project_dir, args.estimate)
```

- [ ] **Шаг 5: Убедиться, что тесты проходят**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_factory_cli.py -q
```

Ожидание: 18 passed.

- [ ] **Шаг 6: Прогнать полный набор и закоммитить**

Ожидание: **293 passed**.

```bash
git add scripts/factory.py scripts/factory/preprod.py tests/test_factory_cli.py
git commit -m "feat(preprod): петля обратной связи и потолок бюджета автономного режима"
```

---

## Task 8: Скиллы этапов и драйвер

Код к этому моменту умеет всё механическое. Скиллы добавляют процесс — то, что делает Claude.

**Files:**
- Create: `.claude/skills/factory/SKILL.md`, `.claude/skills/factory-research/SKILL.md`, `.claude/skills/factory-story/SKILL.md`, `.claude/skills/factory-script/SKILL.md`, `.claude/skills/factory-characters/SKILL.md`, `.claude/skills/factory-storyboard/SKILL.md`, `.claude/skills/factory-feedback/SKILL.md`
- Modify: `CLAUDE.md`, `README.md`

**Interfaces:**
- Consumes: CLI из задач 4 и 7, стадия `characters` из задачи 6, формат плейсхолдеров из задачи 5.

- [ ] **Шаг 1: Общий каркас скилла этапа**

Все пять скиллов этапов имеют одинаковый костяк. Пример — `.claude/skills/factory-script/SKILL.md`:

```markdown
---
name: factory-script
description: Написать сценарий серии по одобренным идее и сквозному сюжету. Этап 4 конвейера. Триггер - /factory-script
---

# Сценарий серии

## Перед работой

1. Проверь гейт. Закрыт — остановись и покажи причины, ничего не пиши:

```bash
python scripts/factory.py check --project <проект> --stage script --episode <ep>
```

2. Прочитай ровно это, не больше: `bible/idea.md`, `bible/season-arc.md`,
   `bible/craft-notes.md` (свод правил по ремеслу этого проекта — соблюдай его),
   `project.json` (аудитория, длительность серии, язык).

## Что написать

`episodes/<ep>/script.md` со `status: draft` во frontmatter. Серия разбита на биты
по `quality_mode` (5 или 10 секунд на отрезок) — по биту на будущий видеоотрезок.
У бита: что происходит, реплики персонажей, метки звуковых событий.

Длительность серии — из `project.json.episode_duration_sec`. Число битов должно
сходиться с ней, иначе раскадровка не соберётся.

## После записи

1. Закоммить файл сразу, до правок человека — это базовая версия для `factory.py diff`.
2. Покажи дайджест и остановись: поэпизодный пересказ серии + ключевые диалоги +
   что изменилось после прошлых правок пользователя + открытые вопросы.
3. **Не проставляй `status: approved` сам.** Одобряет человек командой
   `python scripts/factory.py approve --project <проект> episodes/<ep>/script.md`.
```

- [ ] **Шаг 2: Написать остальные четыре скилла этапов**

По тому же каркасу, отличается середина:

- `factory-research` — этап 2, необязательный. Веб-поиск по теме из `project.json`,
  выход `research.md`. Гейта нет, чекпоинта нет.
- `factory-story` — этап 3. Выход: `bible/idea.md`, `bible/season-arc.md`,
  `bible/style-guide.md`. В стайл-гайде обязателен блок между маркерами
  `<!-- canonical:style -->` и `<!-- /canonical:style -->` — без него раскадровка не
  развернёт плейсхолдер. Дайджест: пересказ на 7–10 предложений + логлайн каждой серии
  строкой.
- `factory-characters` — этап 5. Выход: карточки `bible/characters/<name>.md` с
  обязательным блоком `<!-- canonical:appearance -->` и полем `voice` (описание тембра
  словами; аудиопроба не генерится, Фаза 4 отложена). После одобрения карточек —
  генерация референсов: `python scripts/generate_batch.py --project <проект> --episode
  <ep> --stage characters`. Дайджест: карточка на каждого + референс.
- `factory-storyboard` — этап 6. Выход: `episodes/<ep>/shots.json`. Промпты кадров
  пишутся **с плейсхолдерами** `{{style}}` и `{{char:<имя>}}`, а не копиями блоков.
  `refs` кадра содержит `bible/characters/<имя>-ref.png` для каждого объявленного
  персонажа. Чекпоинта нет — дальше гейт трат.

- [ ] **Шаг 3: Драйвер автономного режима**

`.claude/skills/factory/SKILL.md`:

```markdown
---
name: factory
description: Запустить контент-завод в автономном режиме - идти по этапам до ближайшего чекпоинта или до конца, в зависимости от project.json autonomy. Триггер - /factory
---

# Контент-завод, автономный режим

## Цикл

1. Спроси следующий шаг:

```bash
python scripts/factory.py next --project <проект>
```

Вывод `всё закрыто` — работа кончена, доложи и остановись.

2. Вызови скилл этапа: `story` → factory-story, `script` → factory-script,
   `characters` → factory-characters, `storyboard` → factory-storyboard.

3. Дойдя до чекпоинта, действуй по `project.json.autonomy`:

| autonomy | на чекпоинте |
|---|---|
| `checkpoints` (дефолт) | показать дайджест и **остановиться** |
| `auto_approve` | вызвать `factory.py approve`, идти дальше |
| `full` | вызвать `factory.py approve`, идти дальше, тратить без вопросов в пределах `budget_usd` |

При `auto_approve` и `full` в дайджесте всё равно скажи, что одобрил сам.

4. Вернись к шагу 1. Эпизоды идут по порядку и не заканчиваются на первом.

## Бюджет

При `autonomy: full` перед каждой платной стадией спроси код, а не считай сам:

```bash
python scripts/factory.py budget --project <проект> --estimate <сумма из сметы>
```

Код 3 — остановись и доложи, батч не урезай. Смету печатает `generate_batch`
перед подтверждением.

## Чего не делать

- Не проставлять `approved` в обход `factory.py approve`.
- Не запускать платную стадию при закрытом гейте — код 2 и 3 обходить нельзя.
- Не продолжать после `BLOCKED` от любого этапа.
```

- [ ] **Шаг 4: Скилл обратной связи**

`.claude/skills/factory-feedback/SKILL.md`:

```markdown
---
name: factory-feedback
description: Разобрать правки пользователя в творческих артефактах и записать выводы правилами в craft-notes. Триггер - /factory-feedback
---

# Разбор обратной связи

## Что делаешь

1. `python scripts/factory.py status --project <проект>` — найди артефакты с
   `feedback: pending` (человек правил, причина не разобрана) и `feedback: none`
   (ни правок, ни оценки).

2. По каждому `pending`:
   - `python scripts/factory.py diff --project <проект> <артефакт>` — что изменилось;
   - **сформулируй свою догадку о причине правки** и покажи её пользователю;
   - получив подтверждение или поправку, выведи из этого **правило**.

3. По каждому `none` спроси оценку 1–5 и комментарий. Пропуск — оставить `none`.
   **`none` означает «неизвестно», а не «хорошо».** Не записывай в craft-notes ничего
   на основании молчания.

## Как писать в craft-notes

`bible/craft-notes.md` — **свод правил, а не журнал**. Пишется вывод, а не реплика.
Формат: правило в повелительном наклонении, однострочная причина, происхождение.

```markdown
## Диалоги
- Не давать персонажу проговаривать то, что зритель уже видит в кадре —
  реплика дублирует картинку и тормозит сцену. (ep01/script, 2026-08-02)
```

Группы: Сюжет, Диалоги, Персонажи, Визуальные описания.

Близкое правило **не дублируй** — уточни существующее.

**Правило показывай пользователю до записи.** Неверно выведенное правило хуже
отсутствующего: оно молча применится ко всем следующим сериям.

Записав, отметь артефакт:

```bash
python scripts/factory.py feedback --project <проект> <артефакт> --state recorded
```

Оценку 1–5 в craft-notes не пиши — она нужна для тренда по сериям, а не для правил.
```

- [ ] **Шаг 5: Обновить документацию**

В `CLAUDE.md`, в «Правила», добавить:

```markdown
- Первая половина конвейера (бриф → shots.json) — спека
  docs/superpowers/specs/2026-08-02-preproduction-pipeline-design.md. Состояние
  одобрения живёт во frontmatter артефакта вместе с хешом тела и хешами зависимостей;
  `status: approved` ставит ТОЛЬКО `scripts/factory.py approve`, ни скилл, ни другой код.
- Промпты кадров в shots.json содержат плейсхолдеры `{{style}}` и `{{char:<имя>}}`;
  разворачивает их `factory.prompts.expand_prompt` перед сабмитом, развёрнутый текст
  пишется в манифест полем `prompt_sent`.
- `bible/craft-notes.md` — свод правил по ремеслу проекта, читается каждой творческой
  стадией. Молчание пользователя не считается одобрением: `feedback: none` означает
  «неизвестно».
```

В `README.md` — заменить пункт «Первый этап конвейера — от брифа к `shots.json` — пока
делается вручную, автоматизация запланирована» на описание новых команд и скиллов.

- [ ] **Шаг 6: Прогнать полный набор и закоммитить**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **294 passed** (скиллы — markdown, тестов не добавляют).

```bash
git add .claude/skills CLAUDE.md README.md
git commit -m "feat(preprod): скиллы этапов, драйвер автономного режима и петля обратной связи"
```

---

## Порядок и зависимости

```
Task 1 (артефакт: frontmatter + хеш)
   └─► Task 2 (состояние, устаревание)
          └─► Task 3 (гейты, next_stage)
                 ├─► Task 4 (CLI)
                 │      └─► Task 7 (feedback, diff)
                 └─► Task 6 (стадия characters)

Task 5 (плейсхолдеры) — зависит только от Task 1, можно вести параллельно с 2-4

Task 8 (скиллы) — последней: опирается на всё
```

Задачи 1–7 — чистый Python без сети, деньги не тратятся. Живых генераций в этом плане
нет вовсе: первая платная проверка — прогон `--stage characters` на реальном проекте,
уже после мержа.

## Приёмка

`python scripts/factory.py init` на свежем проекте создаёт дерево; `next` ведёт по
этапам; `check` отдаёт 3 на закрытом гейте и 0 на открытом; `approve` фиксирует хеши,
и правка одобренного файла переводит его в `stale_self`, а правка его основания — в
`stale_deps`; `generate_batch --stage characters` генерирует референсы через манифест
и ревью; `--stage storyboard` разворачивает плейсхолдеры и пишет отправленный промпт
в манифест; `status` показывает колонку feedback, где `none` читается как «неизвестно».
