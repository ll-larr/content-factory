# Починка находок ревью + работа с графом — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть находки ревью 2026-08-02, привести граф знаний в рабочее состояние и провести первый живой прогон пре-продакшна.

**Architecture:** три независимых трека. Первый — настоящие дефекты корректности, которые уже сейчас портят данные или тратят деньги впустую. Второй — устойчивость, структура и правда в документации. Третий — граф: dangling-рёбра, уборка устаревшего каталога, регламент обновления. Живой прогон стоит между первым и вторым: он найдёт класс ошибок, который ревью не находит в принципе.

**Tech Stack:** Python 3.12, pytest, PyYAML, ffmpeg, graphify.

**Источники:** ревью 2026-08-02 (эта сессия), финальное ревью ветки `feat/preproduction`, журнал `.superpowers/sdd/progress.md`.

## Global Constraints

- Все команды — **из корня репо** `C:\Users\lar\content-factory`.
- Тесты: `.\.venv\Scripts\python.exe -m pytest -q`. venv **не активировать**.
- Отправная точка: **333 passed** на `master` (`0405d44`). Перед каждым коммитом набор зелёный, вывод чистый.
- Стиль репо: докстроки и комментарии по-русски, технические термины английские.
- Изоляция провайдера: специфика провайдера только в `scripts/factory/providers/<name>.py` и `knowledge/<name>-api.md`.
- `status: approved` ставит только `scripts/factory.py approve`.
- Гейт трат не обходить: коды 2 и 3 — отказ, а не предложение урезать батч.
- В конец тела коммита — `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## С чего начинать и почему

Задачи 1–3 — настоящие дефекты: первый уже портит данные в репозитории, второй и третий тратят деньги на заведомо негодный результат. Их закрыть первыми.

Дальше — **задача 8, первый живой прогон**. Это важнее оставшейся полировки: конвейер пре-продакшна ни разу не работал на реальном проекте, а все восемь задач его постройки проверялись только тестами и ревью. Ревью не находит того, что находит первый прогон — например, что дайджест нечитаем, что скилл спрашивает не то или что модель пишет `characters:` не в том формате. Полировать код, который ещё ни разу не выполнил свою работу, — не лучший порядок.

Задачи 4–7 и 9–10 можно вести после прогона в любом порядке.

---

## Task 1: Парсер frontmatter в `models.py` теряет данные

**Активный дефект, воспроизведён.** `load_card` ищет разделитель подстрокой `text.split("---", 2)`. `knowledge/_template.md` содержит внутри своего frontmatter строку `# --- Карта провайдеров (FINAL §5.5) ... ---`, поэтому шаблон **уже сейчас** грузится без блока `providers`:

```
ключи frontmatter шаблона: ['id','type','family','status','supports_start_end_frame',
                            'native_audio','max_clip_seconds','allowed_durations',
                            'aspect_ratios','cost_tier']
providers на месте: False
```

Скопировавший шаблон получает карточку без провайдеров и код 2 «not available on provider» без намёка на причину. Ровно этот баг был найден и починен в `artifact.py` (задача 1 ветки пре-продакшна) — в `models.py` его не перенесли.

**Files:**
- Modify: `scripts/factory/artifact.py` (вынести разбор в общий хелпер)
- Modify: `scripts/factory/models.py:13-29`
- Test: `tests/test_models.py`, `tests/test_artifact.py`

**Interfaces:**
- Produces: `factory.artifact.split_frontmatter(text: str, path) -> tuple[dict, str]` — разбирает документ на meta и тело, ищет разделитель построчно; поднимает `ArtifactError`.
- Consumes: `models.load_card` использует его же и оборачивает ошибку в `ModelError`.

- [ ] **Шаг 1: Написать падающий тест**

В `tests/test_models.py`:

```python
def test_template_card_keeps_providers_block():
    """Реальный knowledge/_template.md содержит '---' внутри frontmatter.
    Поиск разделителя подстрокой отрезал блок providers, и карточка,
    скопированная из шаблона, отбивалась гейтом без объяснения причины."""
    card = load_card(Path("knowledge/_template.md"))
    assert "providers" in card, card.keys()


def test_card_value_with_dashes_survives(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("---\nid: x\ntype: image\nstatus: skeleton\n"
                 "note: до---после\nproviders: {wavespeed: {id: a}}\n---\n# X\n",
                 encoding="utf-8")
    card = load_card(p)
    assert card["note"] == "до---после"
    assert "providers" in card
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_models.py -k "template_card or dashes" -q
```

Ожидание: FAIL — `assert 'providers' in card`.

- [ ] **Шаг 3: Вынести разбор в общий хелпер**

В `scripts/factory/artifact.py` заменить тело `load_artifact` на использование нового хелпера и добавить его же:

```python
def split_frontmatter(text: str, path) -> tuple[dict, str]:
    """Разобрать документ на YAML-frontmatter и тело.

    Разделитель ищется ПОСТРОЧНО, а не подстрокой: значение внутри frontmatter,
    содержащее '---' (логлайн с прочерком, комментарий-разделитель в шаблоне
    карточки), иначе разрезает документ не там — meta молча обрезается, телом
    становится склейка. Исключения при этом нет.
    """
    lines = text.splitlines()
    if not lines or not _SEP_LINE_RE.fullmatch(lines[0]):
        raise ArtifactError(f"{path}: нет YAML-frontmatter")
    for i in range(1, len(lines)):
        if _SEP_LINE_RE.fullmatch(lines[i]):
            closing = i
            break
    else:
        raise ArtifactError(f"{path}: frontmatter не закрыт '{_SEP}'")
    try:
        meta = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as e:
        raise ArtifactError(f"{path}: некорректный YAML — {e}") from None
    if not isinstance(meta, dict):
        raise ArtifactError(f"{path}: frontmatter не является YAML-словарём")
    return meta, "\n".join(lines[closing + 1:]).strip()
```

`load_artifact` после этого — три строки: прочитать файл, вызвать хелпер, собрать `Artifact`.

- [ ] **Шаг 4: Перевести `models.load_card` на хелпер**

В `scripts/factory/models.py`:

```python
from factory.artifact import ArtifactError, split_frontmatter


def load_card(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        card, _body = split_frontmatter(text, path)
    except ArtifactError as e:
        raise ModelError(str(e)) from None
    for req in ("id", "type", "status"):
        if req not in card:
            raise ModelError(f"{path}: frontmatter missing {req!r}")
    return card
```

Тело карточки `load_card` по-прежнему отбрасывает — это осознанно, у карточки значима только матрица возможностей.

- [ ] **Шаг 5: Убедиться, что всё зелёное**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **335 passed** (333 + 2). Существующие тесты `test_models.py` про битые карточки должны продолжать работать — сообщения об ошибке те же по смыслу, но текст сменился с английского на русский; если тест сверяет текст, поправить его, а не возвращать старый парсер.

- [ ] **Шаг 6: Коммит**

```bash
git add scripts/factory/artifact.py scripts/factory/models.py tests/test_models.py tests/test_artifact.py
git commit -m "fix(models): разбор frontmatter карточки построчно — шаблон терял блок providers"
```

---

## Task 2: Плейсхолдер внутри канонического блока уезжает провайдеру

`expand_prompt` подставляет блок одним проходом и подставленное не пересматривает. `leftover_braces` смотрит только исходный промпт. Значит `{{...}}`, оказавшийся **внутри** `canonical:style` или `canonical:appearance`, уедет провайдеру буквально и оплатится. Стадия `characters` вставляет appearance-блок вообще без проверок.

**Files:**
- Modify: `scripts/factory/prompts.py`
- Modify: `scripts/generate_batch.py` (ветка `characters`)
- Test: `tests/test_prompts.py`, `tests/test_generate_batch.py`

**Interfaces:**
- Produces: `expand_prompt` после подстановки проверяет результат и поднимает `PromptError`, если в нём остались `{{...}}`.

- [ ] **Шаг 1: Написать падающий тест**

В `tests/test_prompts.py`:

```python
def test_placeholder_inside_canonical_block_is_rejected(tmp_path):
    """Блок стиля с {{...}} внутри: подстановка одним проходом не пересматривает
    вставленное, и фигурные скобки уехали бы провайдеру буквально."""
    body = "<!-- canonical:style -->flat 2D {{char:murzik}}<!-- /canonical:style -->"
    save_artifact(Artifact(path=tmp_path / "bible" / "style-guide.md",
                           meta={"kind": "style-guide", "status": "approved",
                                 "content_sha": body_sha(body)}, body=body))
    with pytest.raises(PromptError, match="после разворачивания"):
        expand_prompt("{{style}} cat", tmp_path)
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_prompts.py -k canonical_block_is_rejected -q
```

Ожидание: FAIL — `DID NOT RAISE`.

- [ ] **Шаг 3: Реализовать**

В `scripts/factory/prompts.py`, в конце `expand_prompt`:

```python
    expanded = _PLACEHOLDER.sub(replace, prompt)
    # Подстановка идёт одним проходом и вставленное не пересматривает. Если
    # фигурные скобки были ВНУТРИ канонического блока, они уцелели бы и уехали
    # провайдеру буквально — оплаченный кадр с '{{...}}' в тексте.
    leftovers = re.findall(r"\{\{[^}]*\}\}", expanded)
    if leftovers:
        raise PromptError(
            f"после разворачивания остались плейсхолдеры {leftovers!r} — "
            "вероятно, они внутри канонического блока")
    return expanded
```

- [ ] **Шаг 4: Закрыть стадию characters**

В `scripts/generate_batch.py`, в ветке `characters` внутри `build_jobs`, после получения `appearance`:

```python
            appearance = canonical_block(card, "appearance")
            stray = _PLACEHOLDER_ANY.findall(appearance)
            if stray:
                raise PromptError(
                    f"{card.name}: в canonical:appearance остались плейсхолдеры "
                    f"{stray!r} — они уехали бы провайдеру буквально")
```

`PromptError` из `build_jobs` уже оборачивается в код 2 (сделано в задаче 5 ветки пре-продакшна), отдельной обработки не нужно.

- [ ] **Шаг 5: Тест на стадию characters**

В `tests/test_generate_batch.py`:

```python
def test_characters_stage_rejects_placeholder_in_appearance(proj, monkeypatch):
    body = ("<!-- canonical:appearance -->orange {{style}} cat"
            "<!-- /canonical:appearance -->")
    save_artifact(Artifact(path=proj / "bible" / "characters" / "murzik.md",
                           meta={"kind": "character", "status": "approved",
                                 "content_sha": body_sha(body)}, body=body))
    write_script(proj, characters=["murzik"])
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 2
    assert fp.submitted == []
```

- [ ] **Шаг 6: Прогнать набор и закоммитить**

Ожидание: **337 passed**.

```bash
git add scripts/factory/prompts.py scripts/generate_batch.py tests/
git commit -m "fix(prompts): плейсхолдер внутри канонического блока больше не уезжает провайдеру"
```

---

## Task 3: Референс персонажа не связан с карточкой

Единственный платный артефакт первой половины остался вне механизма, ради которого вся ветка и строилась. Правишь `canonical:appearance` после `review.py accept` — карточка становится другой, референс остаётся прежним, и кадры генерируются по устаревшей картинке. Ни один гейт этого не замечает.

**Files:**
- Modify: `scripts/factory/manifest.py` (`KNOWN_FIELDS`)
- Modify: `scripts/generate_batch.py` (запись `card_sha`, проверка в ветке `storyboard`)
- Test: `tests/test_generate_batch.py`

**Interfaces:**
- Produces: item манифеста с `kind: character_ref` несёт поле `card_sha` — хеш тела карточки на момент генерации референса.

- [ ] **Шаг 1: Написать падающий тест**

```python
def test_storyboard_blocked_when_character_card_changed_after_reference(proj, monkeypatch):
    """Правка внешности после приёмки референса делает картинку устаревшей:
    кадры сгенерировались бы по описанию, которого уже нет."""
    write_character(proj, "murzik")
    write_script(proj, characters=["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()

    art = load_artifact(proj / "bible" / "characters" / "murzik.md")
    art.body = ("<!-- canonical:appearance -->СЕРЫЙ кот"
                "<!-- /canonical:appearance -->")
    art.meta["content_sha"] = art.sha
    save_artifact(art)

    assert run(proj, "storyboard") == 3
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Ожидание: FAIL — вернётся 0, раскадровка стартует на устаревшем референсе.

- [ ] **Шаг 3: Реализовать**

`scripts/factory/manifest.py` — добавить `card_sha` в `KNOWN_FIELDS`.

`scripts/generate_batch.py`, в цикле генерации при успехе, для `kind == "character_ref"` записывать хеш карточки:

```python
            extra = {}
            if j["kind"] == "character_ref":
                # Референс — единственный платный артефакт первой половины.
                # Без привязки к карточке правка внешности после приёмки не
                # делает картинку устаревшей, и кадры идут по описанию,
                # которого уже нет (находка ревью 2026-08-02).
                extra["card_sha"] = load_artifact(j["card"]).sha
            manifest.set_status(j["item_id"], "generated", file=str(j["dest"]),
                                job_id=job_id, prompt_sent=j["params"].get("prompt"),
                                credits_spent=item["credits_spent"] + estimates[j["item_id"]],
                                **extra)
```

В `build_jobs` для стадии `characters` добавить в job поле `"card": card`, чтобы путь карточки был под рукой.

В ветке `storyboard`, рядом с проверкой принятых референсов:

```python
                stored = manifest.get(item_id).get("card_sha")
                current = load_artifact(
                    project_dir / "bible" / "characters" / f"{name}.md").sha
                if stored and stored != current:
                    not_ready.append(
                        f"{item_id}: карточка изменилась после приёмки референса — "
                        "перегенерируй референс (review.py requeue)")
```

- [ ] **Шаг 4: Прогнать набор и закоммитить**

Ожидание: **338 passed**.

```bash
git add scripts/factory/manifest.py scripts/generate_batch.py tests/test_generate_batch.py
git commit -m "fix(characters): референс устаревает вместе с карточкой персонажа"
```

---

## Task 4: Устойчивость и симметрия (пакетом)

Пять мелких дефектов одного класса — обработка краёв. По одному тесту на каждый.

**Files:**
- Modify: `scripts/factory/prompts.py:45`, `scripts/factory/ffmpeg_tools.py:80`, `scripts/factory.py` (`cmd_feedback`), `scripts/factory/preprod.py` (`episode_ids`, `_STATE_MESSAGE`, `_canonical_re`)
- Test: `tests/test_preprod.py`, `tests/test_factory_cli.py`, `tests/test_prompts.py`

- [ ] **Шаг 1: `except Exception` сузить**

`prompts.py:45` (`has_canonical`) и `ffmpeg_tools.py:80` (`ensure_png`) ловят голый `Exception` — прячут и ошибки программиста. Заменить на `(ArtifactError, OSError)` и `(FfmpegError, OSError)` соответственно.

- [ ] **Шаг 2: `cmd_feedback` не падать на битом артефакте**

`scripts/factory.py`, `cmd_feedback` зовёт `load_artifact` без `try`, тогда как `cmd_approve` и `cmd_status` этот случай обрабатывают. Асимметрия внутри одного CLI:

```python
    try:
        art = load_artifact(path)
    except (ArtifactError, OSError) as e:
        print(f"{rel}: не читается — {e}")
        return 1
```

- [ ] **Шаг 3: `episodes` не должен молча становиться единицей**

`preprod.episode_ids`: `int(data.get("episodes", 1) or 1)` превращает `0` в один эпизод, а отрицательное — в пустой список, из-за чего `next_stage` говорит «всё закрыто» на пустом проекте. Заменить на явное:

```python
    raw = data.get("episodes", 1)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        raise ProjectError(f"episodes должно быть числом, получено {raw!r}") from None
    if count < 1:
        raise ProjectError(f"episodes должно быть >= 1, получено {count}")
```

Тест: `episodes: 0` и `episodes: "три"` дают внятную ошибку, а не тихую единицу.

- [ ] **Шаг 4: `stale_deps` должен называть виноватого**

Сейчас сообщение одинаково для «изменилась», «удалена» и «не разбирается», и не говорит какая. Спека §5 обосновывает отдельное состояние тем, что человек должен понять, чей файл перечитывать — а он узнаёт только, что чужой. Вернуть из `artifact_state` состояние как есть (контракт не менять), но добавить функцию:

```python
def stale_reason(project_dir: Path, path: Path) -> str:
    """Какая именно зависимость сделала артефакт устаревшим."""
```

и использовать её в `stage_gate` при формировании сообщения.

- [ ] **Шаг 5: `re.escape` в `_canonical_re`**

`prompts._canonical_re` подставляет имя в регулярку без экранирования. Сейчас зовётся только литералами `style`/`appearance`, но это разряженное ружьё: `re.escape(name)`.

- [ ] **Шаг 6: Прогнать набор и закоммитить**

```bash
git add scripts/ tests/
git commit -m "fix(preprod): краевые случаи — узкий отлов исключений, симметрия CLI, внятный episodes и stale_deps"
```

---

## Task 5: Цикл импортов `preprod` ↔ `prompts`

`preprod` импортирует `prompts.has_canonical` на уровне модуля; `prompts` импортирует `preprod.artifact_state` и `preprod.is_safe_name` **внутри функций**, чтобы цикл не сомкнулся. Работает, но следующего читателя это озадачит, а любая новая связь между модулями сломается неочевидно.

**Files:**
- Create: `scripts/factory/names.py` (или расширить `artifact.py`)
- Modify: `scripts/factory/preprod.py`, `scripts/factory/prompts.py`

- [ ] **Шаг 1: Определить, что кому принадлежит**

Разорвать цикл можно тремя способами; выбрать до правки кода и записать выбор в докстроку:

1. Вынести `is_safe_name` и `canonical`-хелперы в третий модуль без зависимостей, от которого зависят оба. Самый прямой.
2. Перенести `artifact_state` в `artifact.py` — но он читает `depends_on` и знает про структуру проекта, там ему не место.
3. Оставить как есть, задокументировав. Худший вариант: цикл остаётся, просто с извинением.

Рекомендация — первый: `names.py` с `is_safe_name` и `canonical_block`/`has_canonical` (они про разбор текста, а не про состояние), `prompts.py` остаётся про плейсхолдеры, `preprod.py` про состояние.

- [ ] **Шаг 2: Перенести, убрать функциональные импорты, прогнать набор**

Тесты менять не должно — это чистый рефактор. Если тест пришлось поправить, значит переехало больше задуманного: остановиться и разобраться.

```bash
git add scripts/factory/ tests/
git commit -m "refactor(preprod): разорван цикл импортов preprod и prompts"
```

---

## Task 6: Правда в документации

**Files:**
- Modify: `README.md:322`, `docs/superpowers/specs/2026-08-02-preproduction-pipeline-design.md` §7
- Modify: `scripts/factory.py` (`cmd_approve`) — либо спека

- [ ] **Шаг 1: Счётчик тестов**

`README.md:322` говорит «покрыты 320 тестами», фактически 333. Заменить на актуальное число **и** дописать, как его получить (`pytest -q`), чтобы следующий читатель проверил, а не поверил.

- [ ] **Шаг 2: Пометка авто-одобрения**

Спека §7 обещает: «При `auto_approve` и `full` в `approved_at` артефакта пишется пометка, что одобрение автоматическое — иначе по файлу не отличить решение человека от решения машины». В `cmd_approve` такого флага нет. Два честных выхода:

- реализовать: `factory.py approve --auto` пишет `approved_by: auto` в frontmatter, драйвер зовёт с флагом;
- либо вычеркнуть из спеки с пометкой, почему отказались.

Рекомендация — реализовать: без этого в режиме `full` по проекту невозможно понять, что человек не смотрел ни один чекпоинт, а это ровно тот случай, когда захочется узнать.

- [ ] **Шаг 3: Гейт этапа story**

Спека §5 требует для этапа 3 «валидный `project.json`», но `stage_gate("story")` не проверяет ничего, а CLI смотрит только на существование файла. Битый бриф обнаружится на `generate_batch`, после того как написаны идея, арка и стайл-гайд. Добавить в гейт вызов `load_project` и превратить `ProjectError` в проблему гейта.

```bash
git add README.md docs/ scripts/ tests/
git commit -m "docs+fix: счётчик тестов, пометка авто-одобрения, гейт story проверяет project.json"
```

---

## Task 7: Граф — 102 dangling-ребра

Диагностика после пересборки:

```
raw_edges: 2100
valid_candidate_edges: 1998
dangling_endpoint_edges: 102
```

Сто два ребра ведут в узлы, которых в графе нет. Причина почти наверняка в том, что семантические субагенты придумывают id для сущностей, которые есть только в AST, и промахиваются мимо формата. Это не косметика: рёбра в никуда искажают и сообщества, и betweenness, то есть и подсказки, ради которых граф строится.

**Files:**
- Investigate: `graphify-out/graph.json`, кэш `graphify-out/cache/`

- [ ] **Шаг 1: Выяснить, куда именно ведут висячие рёбра**

```bash
.\.venv\Scripts\python.exe -c "
import json, collections
from pathlib import Path
g = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
ids = {n['id'] for n in g['nodes']}
missing = collections.Counter()
for e in g.get('edges', []):
    for end in (e.get('source'), e.get('target')):
        if end not in ids:
            missing[end] += 1
for tid, c in missing.most_common(30):
    print(c, tid)
print('уникальных отсутствующих узлов:', len(missing))
"
```

- [ ] **Шаг 2: Классифицировать**

Три вероятных класса, и лечатся они по-разному:

- id в старом формате (только имя файла или только ближайший каталог вместо полного пути) — лечится пересборкой с `graphify extract --force`;
- ссылки на внешние сущности (ElevenLabs, pytest, провайдеры) — им нужен собственный узел, а не ребро в пустоту;
- опечатки конкретного субагента — лечатся уточнением промпта чанка.

Записать распределение, прежде чем чинить.

- [ ] **Шаг 3: Починить и пересобрать**

По итогам классификации: либо `graphify extract --force`, либо ручное добавление внешних узлов, либо и то и другое. Приёмка — `dangling_endpoint_edges: 0` в диагностике, или явно записанное объяснение, почему остаток законен.

---

## Task 8: Первый живой прогон пре-продакшна

**Это главная задача плана**, хотя стоит восьмой по номеру. Конвейер построен, отревьюен и покрыт 333 тестами, но ни разу не выполнил свою работу.

**Files:**
- Create: `projects/pilot/project.json`

- [ ] **Шаг 1: Завести пилотный проект**

Мини-серия 60–90 секунд, два персонажа — по базовой спеке §14. `autonomy: checkpoints` (дефолт), чтобы видеть каждый чекпоинт.

- [ ] **Шаг 2: Пройти конвейер вручную, командой за командой**

```bash
python scripts/factory.py init   --project projects/pilot
python scripts/factory.py next   --project projects/pilot
```

Дальше по подсказке `next`: `/factory-story` → `approve` × 3 → `/factory-script` → `approve` → `/factory-characters` → `approve` → `generate_batch --stage characters` → `review.py accept` → `/factory-storyboard`.

- [ ] **Шаг 3: Записывать всё, что окажется неудобным**

Смотреть не на то, работает ли код (тесты это уже сказали), а на то, что видит человек: читаем ли дайджест, понятно ли сообщение закрытого гейта, не спрашивает ли скилл лишнего, в том ли формате модель пишет `characters:`. Каждое наблюдение — строкой в отчёт.

- [ ] **Шаг 4: Прогнать `/factory` в автономном режиме на втором эпизоде**

Проверить именно то, что нельзя проверить тестом: доходит ли драйвер до платной половины этапа персонажей сам, и удерживает ли `budget_usd` при `autonomy: full`.

- [ ] **Шаг 5: Оценить творческий выход**

`/factory-feedback` — первый настоящий проход петли §11. Проверить, что правки видны как `pending`, что догадка о причине формулируется осмысленно и что правило в `craft-notes.md` получается переносимым.

**Приёмка:** `shots.json` первого эпизода написан и проходит гейт `generate_batch --stage storyboard`. Наблюдения записаны в `docs/superpowers/plans/2026-08-03-first-run-notes.md`.

---

## Task 9: Уборка устаревшего графа и регламент обновления

- [ ] **Шаг 1: Удалить `.understand-anything/`**

1.3 МБ снимка, снятого до модулей `artifact.py`, `preprod.py`, `prompts.py`, `factory.py` и стадии `characters`. Каталог в `.gitignore`, из истории ничего не пропадёт. Держать два графа — гарантия однажды посмотреть не в тот.

```bash
rm -rf .understand-anything
```

- [ ] **Шаг 2: Решить, как граф остаётся свежим**

Три варианта, выбрать один и записать в `CLAUDE.md`:

- ручной `graphify <путь> --update` после серии правок — дёшево, но забывается;
- post-commit хук (`references/hooks.md` скилла) — не забывается, но каждый коммит платит;
- `--watch` на время активной работы.

Рекомендация — первый плюс правило в `CLAUDE.md`: обновлять после мержа ветки, а не после каждого коммита. Граф нужен как карта между задачами, а не внутри одной.

- [ ] **Шаг 3: Проверить, что инкрементальный прогон работает**

```bash
graphify . --update
```

Ожидание: пересобираются только изменённые файлы, `dangling_endpoint_edges` не растёт.

---

## Task 10: Ops-долги (выполняет пользователь)

- [ ] **Перевыпустить ключи** `WAVESPEED_API_KEY`, `RUNWARE_API_KEY`, `OPENROUTER_API_KEY`. Засветились в чате 2026-06-17, репозиторий публичный, и это единственный пункт из всех, где промедление имеет цену, растущую со временем.
- [ ] Решить судьбу Фазы 4 (звук): провайдеры TTS/SFX/музыки не выбраны, начинается с прослушивания проб из `spike/duck_calib/voices*` и отдельного brainstorming.

---

## Порядок

```
Task 1 (парсер — портит данные уже сейчас)
Task 2 (плейсхолдер в блоке)          ─┐ дефекты, ведущие к оплате мусора
Task 3 (референс не устаревает)       ─┘
        │
        ▼
Task 8 (ПЕРВЫЙ ЖИВОЙ ПРОГОН) ← главное; найдёт то, чего не находит ревью
        │
        ├──► Task 4 (краевые случаи)
        ├──► Task 5 (цикл импортов)
        ├──► Task 6 (правда в доках)
        ├──► Task 7 (dangling-рёбра графа)
        └──► Task 9 (уборка графа и регламент)

Task 10 — ops, параллельно всему, ключи лучше не откладывать
```

## Что этот план сознательно не трогает

- Фаза 4 (звук) — отдельная подсистема, начинается с brainstorming, не с кода.
- Пилот полной серии 3–5 минут — после выводов мини-серии из задачи 8.
- Шортс-баннер и 9:16 в сборке — отложены ранее, причина не изменилась.
- Живая проверка 1080p и Runware-маппингов остальных карточек — платно и не блокирует.
