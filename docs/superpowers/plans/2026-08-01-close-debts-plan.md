# Закрытие долгов content-factory: мёрж спайка → Runware → seedance → монтаж → звук

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть все накопленные долги роадмапа `2026-07-08-roadmap-next-steps.md` (несмерженный спайк, Runware, хвост Фазы 2, калибровка дакинга, гигиена ключей и путей) и подвести проект к старту Фазы 4 — генерации звука.

**Architecture:** долги закрываются в порядке «сначала бесплатное и разблокирующее, потом платное». Мёрж спайка снимает главную блокировку (в `master` все карточки `skeleton` — конвейер не запускается). Затем два независимых платных трека (Runware / seedance) и один бесплатный (монтаж). Фаза 4 — отдельная подсистема: этот план доводит её только до входа в brainstorming, кода по звуку здесь нет.

**Tech Stack:** Python 3.12, pytest, pyyaml, urllib (без SDK), ffmpeg/ffprobe, git.

## Global Constraints

- Все команды — **из корня репо** `C:\Users\lar\content-factory` (пути `knowledge/` и `projects/` относительные).
- Тесты: `.\.venv\Scripts\python.exe -m pytest -q`. venv **не активировать** — всегда явный путь к интерпретатору.
- Перед каждым коммитом тесты зелёные. Отправная точка: **205 passed** на `master`, **219 passed** на `spike/provider-verification`.
- Изоляция провайдера: точные эндпоинты, model-id/AIR, имена полей — ТОЛЬКО в `scripts/factory/providers/<name>.py` и `knowledge/<name>-api.md`. Больше нигде.
- Ключи — только из env (`WAVESPEED_API_KEY`, `RUNWARE_API_KEY`, `OPENROUTER_API_KEY`), файл `C:\Users\lar\.spike_env` вне репо. В код и конфиги не писать, в чат не вставлять.
- Гейт трат (`status: skeleton` → exit 2) не обходить. Карточка уходит в `verified` только после успешной живой генерации, с датой, фактическим разрешением файла и списанной суммой в комментарии.
- Бюджет живых генераций этой итерации согласован пользователем 2026-08-01 (порядок ~$1 суммарно); отдельного подтверждения на каждую генерацию не требуется, но фактическую смету печатать перед запуском.
- `spike/` — в `.gitignore`. Скрипты спайков не коммитятся; в git уезжают только карточки, доки и код в `scripts/`.
- Каталог `.understand-anything/` — knowledge-graph. Перед правкой файла смотреть обратные рёбра (impact), после серии правок — инкрементальный `/understand`.

## Карта файлов

| Файл | Что делает | Задачи |
|---|---|---|
| `scripts/factory/ffmpeg_tools.py` | обёртки ffmpeg/ffprobe; **добавляется** `ensure_png` | 3 |
| `scripts/generate_batch.py` | вызов `ensure_png` после скачивания кадра | 3 |
| `tests/conftest.py` | **добавляется** фикстура `make_jpeg` | 3 |
| `tests/test_ffmpeg_tools.py` | **новый** — тесты `ensure_png` | 3 |
| `tests/test_generate_batch.py` | тест «кадр нормализуется, отрезок нет» | 3 |
| `scripts/factory/providers/runware.py` | возможный переход на `width`/`height` для видео | 5 |
| `tests/test_providers.py` | тест контракта Runware-видео | 5 |
| `knowledge/runware-api.md` | фиксация живого контракта Runware | 4, 5 |
| `knowledge/images/flux_2_klein.md` | `status: skeleton` → `verified` (Runware) | 4 |
| `knowledge/video/vidu_q2_turbo.md` | Runware-маппинг → `verified` | 5 |
| `knowledge/video/seedance_2_0.md`, `seedance1_5.md` | `status` → `verified` (WaveSpeed) | 6 |
| `scripts/mix_audio.py` | константа `DUCK` + обоснование | 7 |
| `scripts/assemble.py` | решение по нормализации разрешения | 8 |
| `docs/superpowers/plans/2026-08-01-audio-findings.md` | **новый** — выводы аудио-проб 2026-07-09 | 9 |
| `README.md`, `CLAUDE.md`, роадмап | актуализация статусов | 11 |

---

# Фаза 0 — Гигиена и разблокировка (бесплатно)

## Задача 1: Мёрж `spike/provider-verification` → `master`

> **Статус: выполнено 2026-08-01.** Все шаги пройдены как задумано, без расхождений с
> планом — мёрж `22c2065`, 219 passed, гейт снят на 10 файлах, запушено, ветка спайка
> удалена локально и на origin.

Главный долг: ветка висит с 2026-06-17, в ней 6 коммитов — фикс контрактного бага `resolution_style`, +175 строк тестов, 8 verified-карточек, роадмап и хэндофф. Пока не слита, `master` физически неработоспособен: все карточки кадров и отрезков `skeleton`, `generate_batch` возвращает код 2 на любой модели.

**Files:**
- Modify: git-история (мёрж-коммит), без правки файлов вручную

**Interfaces:**
- Produces: `master` с verified-карточками (`z_image_turbo`, `flux_2_klein`, `seedream_v4_5`, `nano_banana_flash`, `nano_banana_2`, `veo3_1_lite`, `vidu_q2_turbo`, `kling3_0`), рабочим `resolution_style` в `wavespeed.py`, роадмапом и хэндоффом в `docs/`. Все последующие задачи стоят на этом.

- [x] **Шаг 1: Проверить, что рабочее дерево чистое и мёрж пройдёт без конфликтов**

```bash
git status --short && git merge-tree --write-tree --name-only master spike/provider-verification; echo "exit=$?"
```

Ожидание: `git status --short` пустой; `exit=0` (проверено 2026-08-01 — конфликтов нет). Если exit≠0 — конфликты в перечисленных файлах, разбирать вручную, не форсировать.

- [x] **Шаг 2: Слить спайк в master**

```bash
git checkout master && git merge --no-ff spike/provider-verification -m "merge spike/provider-verification: 8 моделей verified живьём + card-driven resolution_style"
```

- [x] **Шаг 3: Прогнать тесты**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **219 passed**. Если меньше — не пушить, разбираться.

Факт: 219 passed — совпало с ожиданием.

- [x] **Шаг 4: Проверить, что гейт трат снят**

```bash
git grep -c "^status: verified" -- knowledge
```

Ожидание: 8 карточек моделей + 2 исторические аудио (`mirelo_text_to_audio`, `sonilo_music`) = 10 файлов.

Факт: 10 файлов — совпало с ожиданием.

- [x] **Шаг 5: Запушить и убрать ветку**

```bash
git push origin master && git push origin --delete spike/provider-verification && git branch -d spike/provider-verification
```

---

## Задача 2: Гигиена окружения (ops — выполняет пользователь)

> **Статус: НЕ закрыто.** Шаг 2 (баланс WaveSpeed) фактически выполнен — иначе списания
> $0.90/$0.21 за seedance в Задаче 6 не прошли бы (сравни с остатком $0.11 на 2026-07-08).
> Шаги 1, 3, 4 не подтверждены выполненными. Ключи `WAVESPEED_API_KEY`/`RUNWARE_API_KEY`/
> `OPENROUTER_API_KEY` (кроме факта, что Runware пополнен) остаются непеределанными с
> момента утечки в чат 2026-06-17, копия `D:\content-factory` остаётся неразобранной —
> это осознанный, видимый долг, а не забытая галочка.

Не код: три вещи, которые нельзя починить из репо.

**Files:** нет

- [ ] **Шаг 1: Перевыпустить ключи провайдеров**

Ключи `WAVESPEED_API_KEY`, `RUNWARE_API_KEY`, `OPENROUTER_API_KEY` засветились в чате 2026-06-17 и с тех пор не менялись. Перевыпустить в кабинетах (wavespeed.ai, my.runware.ai, openrouter.ai), старые отозвать, положить новые в `C:\Users\lar\.spike_env`. Через чат новые значения **не пересылать**.

- [x] **Шаг 2: Пополнить WaveSpeed**

Остаток на 2026-07-08 — **$0.11**, задача 7 требует ~$0.70. Пополнить на сумму, покрывающую хвост Фазы 2 с запасом. Runware уже пополнен (подтверждено 2026-08-01).

Факт: пополнено пользователем — Задача 6 живьём списала $0.90 + $0.21 = $1.11, что
на порядок больше остатка $0.11 на 2026-07-08. Отмечено выполненным по этой косвенной
улике (счёт баланса напрямую не выведен в git-историю). Примечание: текст выше ссылается
на «задача 7» как на потребителя бюджета — это опечатка самого плана (расходует деньги
Задача 6, Задача 7/дакинг бесплатна), не трогаю задним числом.

- [ ] **Шаг 3: Разобраться с устаревшей копией `D:\content-factory`**

Копия отстаёт: HEAD `1484a23`, история до переписывания на noreply-email, remote не настроен, нет коммита `resolution_style` и роадмапа. Правки в ней потеряются и конфликтуют с GitHub-историей. Варианты: удалить, либо переклонировать заново с `https://github.com/ll-larr/content-factory`. Держать две расходящиеся копии — источник будущих потерь.

- [ ] **Шаг 4: Проверить, что ключи читаются**

```bash
.\.venv\Scripts\python.exe -c "import os;print({k:bool(os.environ.get(k)) for k in ('WAVESPEED_API_KEY','RUNWARE_API_KEY','OPENROUTER_API_KEY')})"
```

Ожидание: `{'WAVESPEED_API_KEY': True, 'RUNWARE_API_KEY': True, 'OPENROUTER_API_KEY': True}` (после `source ~/.spike_env` в той же сессии).

---

## Задача 3: Честное расширение файла кадра (JPEG сохраняется как `.png`)

> **Статус: выполнено 2026-08-01** (коммиты `f8847f2`, `49e19d8`). Шаги 1–9 пройдены как
> задумано. Разошлось с планом после Шага 9: код-ревью (не предусмотрено этим планом как
> отдельный шаг, но выполнено по факту) нашло 2 Important-находки, которых план не
> предвидел — `ensure_png` сносил временник в `finally` безусловно, при сбое
> `run_ffmpeg` терялись и оригинал, и результат; и `FfmpegError` (не `ProviderError`)
> вылетал из `generate_batch.main()` неперехваченным, обрывая батч вместо возврата
> элемента в `pending`. Фикс в `49e19d8` добавил тесты на оба случая — итог **225 passed**,
> не 223, как ожидал Шаг 8.

Латентный баг из хэндоффа §4.7: WaveSpeed отдаёт JPEG, `frame_path` жёстко даёт `NNN.png` — содержимое верное, расширение врёт. Переименовывать файл нельзя: конвенция путей `episodes/<ep>/storyboard/NNN.png` — контракт, на который ссылаются `refs` в `shots.json`, написанные человеком. Значит нормализуем содержимое, а не имя: если байты не PNG — перекодируем через ffmpeg (уже обязательная зависимость).

**Files:**
- Modify: `scripts/factory/ffmpeg_tools.py` (добавить `ensure_png`)
- Modify: `scripts/generate_batch.py:205` (вызов после `provider.download`)
- Modify: `tests/conftest.py` (фикстура `make_jpeg`)
- Modify: `tests/test_generate_batch.py` (`FakeProvider.download` + новый тест)
- Test: `tests/test_ffmpeg_tools.py` (новый)

**Interfaces:**
- Produces: `ensure_png(path: Path) -> Path` — возвращает тот же путь; PNG оставляет байт-в-байт, не-PNG перекодирует на месте.
- Consumes: `run_ffmpeg(args: list[str]) -> None` из того же модуля.

- [x] **Шаг 1: Добавить фикстуру JPEG в conftest**

В `tests/conftest.py`, после фикстуры `make_tone`:

```python
@pytest.fixture
def make_jpeg():
    """Картинка-заглушка в JPEG (lavfi color) — имитирует ответ WaveSpeed."""
    def _make(path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(["-f", "lavfi", "-i", "color=c=blue:s=64x36:d=1",
                 "-frames:v", "1", "-f", "mjpeg", str(path)])
        return path
    return _make
```

- [x] **Шаг 2: Написать падающий тест**

Создать `tests/test_ffmpeg_tools.py`:

```python
"""Тесты обёрток ffmpeg. ffmpeg обязателен в PATH (см. conftest)."""
from factory.ffmpeg_tools import ensure_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_ensure_png_converts_jpeg_saved_under_png_name(tmp_path, make_jpeg):
    """WaveSpeed отдаёт JPEG, а конвейер хранит кадр как NNN.png — чиним содержимое."""
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    assert dest.read_bytes()[:2] == b"\xff\xd8"

    assert ensure_png(dest) == dest
    assert dest.read_bytes()[:8] == PNG_MAGIC


def test_ensure_png_leaves_real_png_byte_identical(tmp_path):
    """Настоящий PNG не трогаем — лишняя перекодировка запрещена."""
    dest = tmp_path / "001.png"
    original = PNG_MAGIC + b"payload-not-a-valid-png-body"
    dest.write_bytes(original)

    ensure_png(dest)
    assert dest.read_bytes() == original


def test_ensure_png_leaves_no_temp_files(tmp_path, make_jpeg):
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    ensure_png(dest)
    assert [p.name for p in tmp_path.iterdir()] == ["001.png"]
```

- [x] **Шаг 3: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_tools.py -q
```

Ожидание: FAIL — `ImportError: cannot import name 'ensure_png' from 'factory.ffmpeg_tools'`.

- [x] **Шаг 4: Реализовать `ensure_png`**

В `scripts/factory/ffmpeg_tools.py` добавить `import os` к импортам и функцию в конец файла:

```python
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def ensure_png(path: Path) -> Path:
    """Гарантировать, что файл с именем *.png действительно PNG.

    WaveSpeed на image-моделях отдаёт JPEG, а конвейер хранит кадры под именем
    NNN.png — конвенция путей (factory.shots.frame_path), на неё ссылаются refs
    в shots.json. Имя менять нельзя, поэтому нормализуем содержимое.
    """
    path = Path(path)
    if path.read_bytes()[:8] == PNG_MAGIC:
        return path
    src = path.with_suffix(path.suffix + ".src")
    os.replace(path, src)
    try:
        run_ffmpeg(["-i", str(src), str(path)])
    finally:
        src.unlink(missing_ok=True)
    return path
```

- [x] **Шаг 5: Убедиться, что тест проходит**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_tools.py -q
```

Ожидание: 3 passed.

- [x] **Шаг 6: Подключить вызов в конвейер**

В `scripts/generate_batch.py` дописать импорт рядом с остальными `factory`-импортами:

```python
from factory.ffmpeg_tools import ensure_png
```

и в цикле генерации, сразу после `provider.download(job_id, j["dest"])`:

```python
            provider.download(job_id, j["dest"])
            if j["kind"] == "frame":
                # провайдер может отдать JPEG под именем .png — нормализуем
                ensure_png(j["dest"])
```

- [x] **Шаг 7: Починить фейковый провайдер и добавить тест интеграции**

В `tests/test_generate_batch.py` заменить тело `FakeProvider.download` (сейчас пишет `b"x"` — не PNG, `ensure_png` уронит на нём ffmpeg):

```python
    def download(self, job_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n")
        return Path(dest)
```

и добавить тест в конец файла:

```python
def test_frames_are_normalized_to_png_segments_are_not(proj, monkeypatch):
    """ensure_png зовётся на кадрах и не зовётся на отрезках (там .mp4)."""
    calls = []
    monkeypatch.setattr(gb, "ensure_png", lambda p: calls.append(Path(p)))
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    assert [p.name for p in calls] == ["001.png", "002.png", "003.png"]

    m = Manifest(proj / "manifest.json")
    for n in (1, 2, 3):
        m.set_status(f"ep01/storyboard/{n:03d}", "done")
    m.save()
    calls.clear()
    fake_provider(monkeypatch)
    run(proj, "segments")
    assert calls == []
```

- [x] **Шаг 8: Прогнать весь набор**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Ожидание: **223 passed** (219 + 3 новых в `test_ffmpeg_tools` + 1 в `test_generate_batch`).

Факт: сначала 223, как и ожидалось. Финальные 225 — уже после ревью-фикса `49e19d8`
(см. пометку у заголовка задачи), в этот шаг они не входили.

- [x] **Шаг 9: Коммит**

```bash
git add scripts/factory/ffmpeg_tools.py scripts/generate_batch.py tests/conftest.py tests/test_ffmpeg_tools.py tests/test_generate_batch.py && git commit -m "fix(frames): нормализация кадра в настоящий PNG (WaveSpeed отдаёт JPEG)"
```

---

# Фаза 1 — Runware живьём (роадмап Фаза 1.2)

Баланс пополнен пользователем 2026-08-01, блокер снят. После мержа в карточках лежат реальные AIR из `modelSearch`: `flux_2_klein` = `runware:400@2`, `vidu_q2_turbo` = `vidu:3@2`, `seedance1_5` = `bytedance:seedance@1.5-pro`.

## Задача 4: Живая image-генерация Runware

> **Статус: выполнено 2026-08-01, разошлось с планом.** Задача 4 предполагала, что
> `scripts/factory/providers/runware.py` трогать не придётся (в «Files» ниже его нет) —
> живая проба (Шаг 2) показала иначе: первый запуск упал HTTP 400
> `missingDimensionParameters` — исход, которого не было среди «Ошибка insufficientCredits
> / Ошибка про architectureId» в ожидании Шага 2. Причина: `imageInference` требует
> целые `width`/`height`, а не строку `resolution` — Шаг 3 плана предполагал этот класс
> бага только для видео-моделей (Задача 5), реальность показала, что и image тоже.
> Из-за этого код-фикс `runware.py` стал общим для Задачи 4 и Задачи 5 (коммит `51f52b7`,
> width/height + `deliveryMethod=async` сразу для image и video) — задачи в итоге
> делались вместе, не последовательно двумя независимыми коммитами, как предполагал план.
> Коммитов вместо одного «feat(knowledge): flux_2_klein verified на Runware живьём» вышло
> четыре: `d1c40c1` (зафиксировать блокер), `51f52b7` (код-фикс), `4b341a0` (гейт
> `preflight_problems`, см. пометку в Задаче 5), `1c9231b` (причесать шапку контракта).
> Итог по факту: `flux_2_klein` verified, 1280x720 MJPEG, $0.00169.

**Files:**
- Create: `spike/live_runware_image.py` (не коммитится — `spike/` в `.gitignore`)
- Modify: `knowledge/images/flux_2_klein.md` (frontmatter `status`)
- Modify: `knowledge/runware-api.md` (раздел с итогами)

**Interfaces:**
- Consumes: `get_provider("runware")` → `RunwareProvider` с методами `estimate/submit/wait/download` (`scripts/factory/providers/base.py`).
- Produces: `flux_2_klein.status == "verified"` — снимает гейт трат для Runware-кадров.

- [x] **Шаг 1: Написать скрипт живой пробы**

Создать `spike/live_runware_image.py` (по образцу `spike/live_phase2_image.py`):

```python
"""Живая проба Runware: один кадр flux_2_klein (AIR runware:400@2).

Запуск из корня: .venv/Scripts/python.exe spike/live_runware_image.py
Ключ — из env RUNWARE_API_KEY. Одна генерация за запуск.
"""
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from factory.providers import get_provider

PROMPT = "orange cartoon cat sitting on a fence, flat 2D animation style"


def main() -> int:
    p = get_provider("runware")
    est = p.estimate("flux_2_klein", {})
    print(f"смета: ${est:.4f}")
    job = p.submit("flux_2_klein", {"prompt": PROMPT, "aspect_ratio": "16:9",
                                    "resolution": "720p"})
    print(f"job: {job}")
    p.wait(job, timeout_sec=300, interval_sec=5)
    dest = Path("spike/live_rw_flux_2_klein.png")
    p.download(job, dest)
    print(f"OK: {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [x] **Шаг 2: Запустить**

```bash
.venv/Scripts/python.exe spike/live_runware_image.py
```

Ожидание: печатается смета (~$0.008), затем `OK: spike/live_rw_flux_2_klein.png` с ненулевым размером. Ошибка `insufficientCredits` означает, что баланс не дошёл — остановиться и сказать пользователю. Ошибка про `architectureId` означает неверный AIR — сверить `modelSearch`, не гадать.

- [x] **Шаг 3: Проверить фактическое разрешение файла**

```bash
ffprobe -v error -show_entries stream=width,height,codec_name -of default=noprint_wrappers=1 spike/live_rw_flux_2_klein.png
```

Записать вывод — он идёт в комментарий карточки. Если пришёл квадрат вместо 16:9 — Runware, как и WaveSpeed, игнорирует `resolution` в пользу другого поля; это вход в задачу 5, зафиксировать факт.

- [x] **Шаг 4: Обновить карточку**

В `knowledge/images/flux_2_klein.md` заменить строку `status:` на (подставить реальные значения из шагов 2–3):

```yaml
status: verified          # Runware подтверждён живьём 2026-08-01 (runware:400@2, $X.XXX списано, файл WxH <формат>); WaveSpeed НЕ проверен
```

- [x] **Шаг 5: Дописать итог в контракт провайдера**

В конец `knowledge/runware-api.md` добавить раздел с датой, фактическим ответом `getResponse` (какие поля пришли, что было в `cost`), подтверждённой семантикой `status` и фактическим разрешением. Это закрывает оговорку из шапки файла «без живого спайка».

- [x] **Шаг 6: Тесты и коммит**

```bash
.\.venv\Scripts\python.exe -m pytest -q && git add knowledge/ && git commit -m "feat(knowledge): flux_2_klein verified на Runware живьём"
```

Ожидание: 223 passed (карточки читаются `test_models.py::test_all_real_knowledge_cards_load`).

---

## Задача 5: Закрыть открытый вопрос Runware — `resolution` против `width`/`height`

> **Статус: выполнено 2026-08-01, код и часть шагов слиты с Задачей 4.** Фикс сделан не
> отдельным прогоном «сначала сломанный video, потом чиним» (Шаг 2, три исхода) —
> `knowledge/runware-api.md` документирует только успешный video-прогон уже ПОСЛЕ
> width/height-фикса; отдельного проваленного video-запроса на строке `resolution` в
> контракте не зафиксировано (фикс обобщили с image, не передоказывали на video отдельно).
> Реализация (`51f52b7`) вышла проще черновика Шага 5: вместо словаря `_WH` с тремя
> разрешениями (480p/720p/1080p) и ветвления `is_image` — единый словарь `_RESOLUTIONS`
> только с `"720p"` (1080p сознательно не замаплен: для FLUX.2 Klein 9B 1080 не кратно
> шагу 16, единой пары px без искажения аспекта для обеих задач карточки нет — см.
> комментарий в `scripts/factory/providers/runware.py:15-30`), и одна ветка кода вместо
> `if is_image/else` — картинка и видео используют одну и ту же пару размеров. Тест вышел
> под другим именем (`test_runware_video_submit_sends_width_height`, не
> `test_runware_video_sends_width_height`, плюс отдельный `test_runware_image_submit_sends_width_height`,
> которого план не предполагал вовсе, и `test_runware_aspect_ratio_9x16_swaps_dimensions`).
> Сверх плана — Шаг 5 не упоминает: обнаружен и закрыт независимый баг `deliveryMethod`
> (sync по умолчанию для image, async для video — `wait()` поллил уже закрытую задачу),
> и добавлен гейт `preflight_problems` (`scripts/factory/providers/base.py`,
> `generate_batch.py: _validation_gate`) — цена на незамапленный `resolution` (например
> 1080p) теперь отбивается ДО сметы, а не только в `submit`. Итог по факту: `vidu_q2_turbo`
> verified, файл 1284x716 (не ровно 1280x720 — Runware сам подгоняет размеры под модель).

Открытый вопрос из `knowledge/runware-api.md`: часть видео-моделей Runware ждёт целочисленные `width`/`height`, а адаптер шлёт строку `resolution` (`runware.py:38-39`). Спайк 2026-06-17 до него не дошёл — баланс отбил раньше. Это ровно тот класс бага, что уже поймали на WaveSpeed (`resolution_style`): кадры молча выходят не того размера.

**Files:**
- Create: `spike/live_runware_video.py` (не коммитится)
- Modify: `scripts/factory/providers/runware.py:36-39` (только если живой ответ докажет необходимость)
- Modify: `knowledge/video/vidu_q2_turbo.md`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `RunwareProvider.submit(model: str, params: dict) -> str`; `params` содержит `prompt`, `duration`, `resolution`, `start_frame`, `end_frame`, `tier`.
- Produces: подтверждённый (или исправленный) контракт видео-сабмита Runware.

- [x] **Шаг 1: Написать скрипт живой пробы видео**

Создать `spike/live_runware_video.py`:

```python
"""Живая проба Runware video: vidu_q2_turbo (AIR vidu:3@2), 5с 720p start→end.

Запуск из корня: .venv/Scripts/python.exe spike/live_runware_video.py
Кадры — коты из прошлого спайка (spike/cat1.png, spike/cat2.png).
"""
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from factory.providers import get_provider

PARAMS = {"prompt": "orange cartoon cat walks along fence, smooth motion",
          "duration": 5, "resolution": "720p",
          "start_frame": "spike/cat1.png", "end_frame": "spike/cat2.png"}


def main() -> int:
    p = get_provider("runware")
    est = p.estimate("vidu_q2_turbo", {"resolution": "720p", "duration": 5})
    print(f"смета: ${est:.4f}")
    job = p.submit("vidu_q2_turbo", PARAMS)
    print(f"job: {job}")
    p.wait(job, timeout_sec=900, interval_sec=10)
    dest = Path("spike/live_rw_vidu_q2_turbo.mp4")
    p.download(job, dest)
    print(f"OK: {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
```

- [x] **Шаг 2: Запустить и снять фактическое разрешение**

```bash
.venv/Scripts/python.exe spike/live_runware_video.py
```

Затем:

```bash
ffprobe -v error -show_entries stream=width,height -show_entries format=duration -of default=noprint_wrappers=1 spike/live_rw_vidu_q2_turbo.mp4
```

Три исхода:
- **HTTP-ошибка про неизвестное поле `resolution`** → модель требует `width`/`height`, идти в шаг 3.
- **Файл пришёл, но не 1280x720** (например квадрат) → `resolution` молча игнорируется, идти в шаг 3.
- **Файл 1280x720, длительность ~5с** → контракт верен, шаг 3 пропустить, идти в шаг 6.

- [x] **Шаг 3: Написать падающий тест на width/height**

Только если шаг 2 показал проблему. В `tests/test_providers.py` добавить сразу после `test_runware_submit` (фикстура `kdir` и хелпер `make` — уже в файле, новых не заводить):

```python
def test_runware_video_sends_width_height(kdir, monkeypatch):
    """Видео-модели Runware ждут целочисленные width/height, не строку resolution."""
    captured = {}

    def fake_request(method, url, json_body=None):
        captured.update(body=json_body)
        return {"data": [{"taskUUID": json_body[0]["taskUUID"]}]}

    p = make("runware", kdir)
    monkeypatch.setattr(p, "_request", fake_request)
    p.submit("seedance_2_0", {"prompt": "m", "duration": 5, "resolution": "720p"})
    task = captured["body"][0]
    assert task["width"] == 1280
    assert task["height"] == 720
    assert "resolution" not in task
```

- [x] **Шаг 4: Убедиться, что тест падает**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_providers.py -k width_height -q
```

Ожидание: FAIL — `KeyError: 'width'`.

- [x] **Шаг 5: Реализовать**

Только если шаг 2 доказал необходимость. В `scripts/factory/providers/runware.py` заменить блок строк 38-39:

```python
        if params.get("resolution"):
            task["resolution"] = params["resolution"]
```

на:

```python
        # Видео-модели Runware принимают целочисленные width/height, а не строку
        # resolution (подтверждено живьём 2026-08-01, см. knowledge/runware-api.md).
        # Аспект — 16:9; для 9:16 (shorts) стороны меняются местами.
        if params.get("resolution"):
            if is_image:
                task["resolution"] = params["resolution"]
            else:
                w, h = _WH[params["resolution"]]
                if params.get("aspect_ratio") == "9:16":
                    w, h = h, w
                task["width"], task["height"] = w, h
```

и добавить рядом с `_ENDPOINT`:

```python
# Пиксельные размеры под строковые разрешения конвейера (контракт — в knowledge/runware-api.md).
_WH = {"480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
```

- [x] **Шаг 6: Прогнать тесты, обновить карточку и контракт**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

В `knowledge/video/vidu_q2_turbo.md` — `status: verified` с датой, фактическим разрешением/длительностью и списанной суммой; в блоке `providers.runware` заменить комментарий «AIR-id подтвердить спайком» на факт. В `knowledge/runware-api.md` — заменить пункт «Часть видео-моделей требует width/height… Сверить по конкретной модели на спайке» на подтверждённый результат.

- [x] **Шаг 7: Коммит**

```bash
git add scripts/factory/providers/runware.py tests/test_providers.py knowledge/ && git commit -m "feat(runware): контракт видео подтверждён живьём, vidu_q2_turbo verified"
```

**Приёмка Фазы 1:** живая генерация Runware проходит без `insufficientCredits`; минимум одна image- и одна video-карточка Runware в `verified`; открытый вопрос `resolution` vs `width/height` закрыт письменно; тесты зелёные.

---

# Фаза 2 — Хвост дефолтных моделей (роадмап Фаза 2)

## Задача 6: Живая проверка `seedance_2_0` и `seedance1_5` на WaveSpeed

> **Статус: выполнено 2026-08-01, с находками сверх плана.** Обе модели verified,
> изменения только в `knowledge/` — тесты не менялись (235 passed, без прироста). Цены
> разошлись сильнее, чем предполагали ценники в описании задачи: `seedance_2_0` списал
> $0.90 против оценки $0.50 (карточка занижала цену вдвое; пересчитана по формуле
> каталога, а не по разовому наблюдению, чтобы смета впредь не занижала). Ещё одна
> находка, которой не было в плане вообще: у `seedance_2_0` `native_audio` стояло
> `false`, хотя живой файл пришёл с aac-дорожкой — поле было ошибкой карточки, исправлено
> на `true`. `seedance1_5` списал $0.21 против оценки $0.20 — план на этом остановился бы,
> но отдельный ревью-проход (коммит `d664a5c`, вне шагов этой задачи) нашёл, что
> `usd_per_sec: 0.052` всё ещё давал смету МЕНЬШЕ факта — округлено вверх до `0.053`,
> заодно уточнена формулировка занижения цены `seedance_2_0` в прозе карточки (~3.6x на
> 1080p, а не «вдвое», как было написано после первого прохода).

Последние два дефолта из FINAL-спеки в статусе `skeleton`. Ждут пополнения WaveSpeed (задача 2, шаг 2). Ценник по карточкам: `seedance_2_0` fast $0.10/с × 5с = **$0.50**; `seedance1_5` pro $0.05/с × 4с = **$0.20**.

Отдельно: у `seedance1_5` сетка длительностей 4/8/12с и она **не совпадает** с отрезками конвейера 5/10с — карточка это прямо отмечает. Живая проба идёт на `duration: 4`, а несовпадение остаётся зафиксированным ограничением, не чинится здесь.

**Files:**
- Modify: `spike/live_phase2_video.py` (добавить кейсы — не коммитится)
- Modify: `knowledge/video/seedance_2_0.md`, `knowledge/video/seedance1_5.md`

- [x] **Шаг 1: Проверить баланс перед тратой (бесплатно)**

```bash
curl -s -H "Authorization: Bearer $WAVESPEED_API_KEY" https://api.wavespeed.ai/api/v3/balance
```

Ожидание: остаток ≥ $0.80. Если меньше — остановиться, сказать пользователю, не пытаться генерировать.

- [x] **Шаг 2: Дописать кейсы в скрипт живых проб**

В `spike/live_phase2_video.py` в словарь `CASES` добавить:

```python
    "seedance_2_0": {"prompt": "orange cartoon cat walks along fence, smooth motion",
                     "duration": 5, "resolution": "720p",
                     "start_frame": "spike/cat1.png", "end_frame": "spike/cat2.png"},
    "seedance1_5": {"prompt": "orange cartoon cat walks along fence, smooth motion",
                    "duration": 4, "resolution": "720p",
                    "start_frame": "spike/cat1.png", "end_frame": "spike/cat2.png"},
```

- [x] **Шаг 3: Запустить обе пробы**

```bash
.venv/Scripts/python.exe spike/live_phase2_video.py seedance_2_0
```

```bash
.venv/Scripts/python.exe spike/live_phase2_video.py seedance1_5
```

Ожидание: обе печатают смету, затем `OK: spike/live_p2_<model>.mp4`. Если WaveSpeed вернёт HTTP 400 про размер — проверить `resolution_style` в карточке (`size` / `k` / `omit`), это уже известный класс бага.

- [x] **Шаг 4: Снять факты по каждому файлу**

```bash
ffprobe -v error -show_entries stream=width,height -show_entries format=duration -of default=noprint_wrappers=1 spike/live_p2_seedance_2_0.mp4
```

То же для `seedance1_5`. Сверить списание с оценкой через `GET /api/v3/balance` до и после — цена, как показал случай vidu, может быть нелинейной.

- [x] **Шаг 5: Обновить обе карточки**

`status: verified` с датой 2026-08-01, фактическим разрешением, длительностью и **фактически списанной** суммой. Если фактическая цена разошлась с `usd_per_sec` в блоке `providers` — поправить цену там же (проза карточки цен не дублирует).

- [x] **Шаг 6: Тесты и коммит**

```bash
.\.venv\Scripts\python.exe -m pytest -q && git add knowledge/video/ && git commit -m "feat(knowledge): seedance_2_0 и seedance1_5 verified на WaveSpeed живьём"
```

**Приёмка Фазы 2:** все дефолтные модели по типам контента (`animated_*`, `film/series`, `shorts/UGC`) — `verified`; `git grep -c "^status: verified" -- knowledge` даёт 12 файлов.

---

# Фаза 3 — Монтаж (бесплатно, можно параллельно с Фазами 1–2)

## Задача 7: Калибровка дакинга

> **Статус: выполнено 2026-08-01, входные варианты не те, что в тексте задачи.** Эта
> задача (и текст выше) отсылает к прослушиванию 2026-07-09 и четырём вариантам
> `A_current_thr005_r8_a20_rel300` / `B_deep_thr003_r12_a10_rel250` /
> `C_gentle_thr01_r4_a50_rel500` / `D_noduck_reference` из `spike/duck_calib/`. По факту
> калибровка 2026-08-01 (коммит `aa39b4a`) переслушала СЕМЬ новых вариантов (A–G + FINAL,
> та же папка `spike/duck_calib`, но не те файлы, что перечислены здесь) — старые
> A/B/C/D упомянуты в комментарии у константы не были. Выбранные параметры дальше от
> Шага 2 плана (пример для «варианта B»: `threshold=0.03:ratio=12:attack=10:release=250`),
> чем предполагалось: итог `threshold=0.01:ratio=20:attack=5:release=1150` — глубже
> (максимальный `ratio`) и с намного более длинным `release` (1150 мс против 250) —
> короткий `release` на прослушивании давал слышимое «дыхание» громкости между фразами.
> Обоснование каждого параметра — в комментарии у `DUCK`, не только «выбор на слух» одной
> строкой, как в примере Шага 2.

`DUCK` в `scripts/mix_audio.py:33` — исходная заглушка `threshold=0.05:ratio=8:attack=20:release=300` с комментарием «параметры уточнить на smoke (Task 6)». Прослушивание 2026-07-09 состоялось: в `spike/duck_calib/` лежат варианты `A_current_thr005_r8_a20_rel300`, `B_deep_thr003_r12_a10_rel250`, `C_gentle_thr01_r4_a50_rel500`, `D_noduck_reference` плюс `DEMO1–6`. **Выводы нигде не записаны, константа не менялась.**

**Files:**
- Modify: `scripts/mix_audio.py:32-33`

**Interfaces:**
- Produces: `DUCK` — строка фильтра ffmpeg `sidechaincompress`, потребляется сборкой фильтр-графа в том же файле. Формат строки не меняется, меняются только числа.

- [x] **Шаг 1: Спросить пользователя, какой вариант выбран**

Это решение на слух, агент его принять не может. Если пользователь не помнит итогов прослушивания 2026-07-09 — переслушать:

```bash
start spike/duck_calib/A_current_thr005_r8_a20_rel300.m4a
```

(и так же B, C, D — `D_noduck_reference` как база сравнения). Вопрос ставить конкретно: «в каком варианте музыка уходит под реплику достаточно, но не проваливается?»

- [x] **Шаг 2: Вписать выбранные параметры с обоснованием**

Заменить строки 32-33 `scripts/mix_audio.py` (числа — из выбранного варианта; ниже пример для B):

```python
# Приглушение музыки под репликами/SFX. Параметры выбраны на слух 2026-07-09
# из вариантов A/B/C/D (spike/duck_calib): threshold ниже — дакинг срабатывает
# и на тихих репликах; ratio выше — реплика не тонет в музыке; короткий attack
# убирает «наезд» музыки на первый слог, длинный release не даёт музыке
# дёргаться между фразами. D (без дакинга) отвергнут: реплики неразборчивы.
DUCK = "sidechaincompress=threshold=0.03:ratio=12:attack=10:release=250"
```

- [x] **Шаг 3: Прогнать тесты монтажа**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_mix_audio.py -q
```

Ожидание: все тесты файла зелёные (они проверяют структуру фильтр-графа, не числа).

- [x] **Шаг 4: Смок на реальном материале**

```bash
.\.venv\Scripts\python.exe scripts/mix_audio.py --project projects/_smoke --episode ep01
```

Ожидание: exit 0, файл `projects/_smoke/episodes/ep01/audio/mix.m4a` перезаписан. Прослушать, подтвердить у пользователя.

- [x] **Шаг 5: Коммит**

```bash
git add scripts/mix_audio.py && git commit -m "feat(mix): калибровка дакинга по прослушиванию 2026-07-09"
```

---

## Задача 8: Зафиксировать решение по нормализации разрешения в сборке

> **Статус: выполнено 2026-08-01**, как рекомендовано планом (коммит `790908d`) —
> пользователь согласился оставить как есть для v1. Формулировка в докстроке
> `assemble.py` совпадает с текстом Шага 1 почти дословно.

`scripts/assemble.py:9-10`: «при разных разрешениях отрезков ffmpeg упадёт с понятной ошибкой — допустимо для v1». Роадмап требует решение зафиксировать: либо чинить, либо осознанно отложить с пометкой.

**Files:**
- Modify: `scripts/assemble.py:9-10` (докстрока) **или** `CLAUDE.md`

- [x] **Шаг 1: Спросить пользователя и зафиксировать**

Рекомендация: **оставить как есть для v1**. Разрешение задаётся в `project.json` на весь проект, разные разрешения внутри эпизода означают ошибку конфигурации, и падение ffmpeg с внятной ошибкой честнее молчаливого апскейла. Если пользователь согласен — заменить в докстроке `assemble.py` фразу «допустимо для v1» на явное решение с датой:

```python
разрешениях отрезков ffmpeg упадёт с понятной ошибкой). Нормализация разрешения
СОЗНАТЕЛЬНО не делается (решение 2026-08-01): разрешение задаётся в project.json
на весь проект, разнобой внутри эпизода — ошибка конфигурации, и падение честнее
молчаливого апскейла. Пересмотреть, если появятся проекты со смешанными отрезками.
```

Если пользователь хочет нормализацию — это отдельная задача с `scale`/`pad` в фильтр-графе, в этот план она не входит.

- [x] **Шаг 2: Коммит**

```bash
git add scripts/assemble.py && git commit -m "docs(assemble): зафиксировано решение не нормализовать разрешение в v1"
```

**Приёмка Фазы 3:** `DUCK` содержит проверенные на слух значения с обоснованием в комментарии; решение по нормализации разрешения записано в коде.

---

# Фаза 4 — Звук (вход в отдельную подсистему)

Здесь плана кода **нет и не должно быть**. Роадмап прямо запрещает писать код Фазы 4 без прохода `superpowers:brainstorming` → `superpowers:writing-plans`: контракт ElevenLabs не исследован (в `knowledge/` его нет вообще), а провайдер SFX и музыки **не выбран** — Higgsfield вырезан, замены нет. Это открытый дизайн-вопрос, а не деталь реализации.

## Задача 9: Зафиксировать выводы аудио-проб 2026-07-09

> **Статус: ОТЛОЖЕНО пользователем 2026-08-01.** Не выполнялась — переслушивание проб не
> состоялось, `docs/superpowers/plans/2026-08-01-audio-findings.md` не создан. Это
> сознательный долг, а не пропуск: Фаза 4 отложена целиком (см. пометку выше и в
> `2026-07-08-roadmap-next-steps.md`), TTS/SFX/музыка остаются без вердикта.

В `spike/duck_calib/voices/` и `voices_design/` лежат пробы TTS (qwen_tts, minimax `lovely_girl` / `russian_handsomechil`, дизайнерские голоса `boy_hero` / `narrator` / `sidekick`), в `spike/duck_calib/` — `audio_mirelo_v2a.wav`, `audio_mmaudio.mp4`, `audio_sonilo_music.mp3`. Выводы не записаны нигде. Это вход в brainstorming Фазы 4 — без письменной фиксации он начнётся с нуля.

**Files:**
- Create: `docs/superpowers/plans/2026-08-01-audio-findings.md`

- [ ] **Шаг 1: Переслушать пробы вместе с пользователем и записать**

Документ должен ответить на три вопроса, по одному разделу на каждый:
1. **TTS:** какой движок звучит приемлемо для мультперсонажей (qwen_tts / minimax / нужен ElevenLabs), что не устроило в отвергнутых.
2. **SFX:** годится ли `mmaudio` (video-to-audio) или `mirelo` как источник эффектов, или нужен отдельный провайдер.
3. **Музыка:** генерировать (чем) или брать стоковые треки — открытый вопрос §16.2 базовой спеки, до сих пор не закрытый.

По каждому пункту — вердикт и причина. «Понравилось / не понравилось» без причины бесполезно для выбора провайдера.

- [ ] **Шаг 2: Коммит**

```bash
git add docs/superpowers/plans/2026-08-01-audio-findings.md && git commit -m "docs(audio): выводы прослушивания проб 2026-07-09"
```

## Задача 10: Вход в brainstorming Фазы 4

> **Статус: ОТЛОЖЕНО пользователем 2026-08-01.** Не выполнялась (зависит от Задачи 9).
> `superpowers:brainstorming` по звуку не запускался, TDD-план Фазы 4 не написан.
> Условие роадмапа «не писать код Фазы 4 без brainstorming → writing-plans» остаётся
> в силе — начинать здесь, когда пользователь вернётся к звуку.

- [ ] **Шаг 1: Запустить `superpowers:brainstorming`**

На вход: `2026-08-01-audio-findings.md`, роадмап §Фаза 4, базовая спека §11 (звук). Решить: объём первого захода (только TTS или сразу TTS+SFX+музыка), провайдер по каждому типу, как аудио-стадия возвращается в `generate_batch.py`, что делать с историческими карточками `knowledge/audio/*` (остаются как референс формата или удаляются).

- [ ] **Шаг 2: Запустить `superpowers:writing-plans`**

Результат — отдельный TDD-план `docs/superpowers/plans/YYYY-MM-DD-audio-generation.md` по образцу `2026-06-15-provider-refactor-design.md`. Ориентировочный состав работы (из роадмапа, не план): адаптер `scripts/factory/providers/elevenlabs.py`, карточки `knowledge/audio/elevenlabs_*.md` и `knowledge/elevenlabs-api.md`, возврат стадии `audio` в `generate_batch.py`, живой спайк на реальных ключах.

---

# Финал

## Задача 11: Актуализация документации и графа

> **Статус: частично выполнено 2026-08-01.** Шаги 1–3 сделаны этой правкой. Мандат этого
> прохода (отдельные инструкции задачи 11) явно ограничил объём до трёх файлов —
> `README.md`, `CLAUDE.md`, два файла в `docs/superpowers/plans/` — и явно запретил
> трогать код/тесты. Из-за этого Шаг 4 (`/understand`, пересборка knowledge-graph) и
> Шаг 5 (финальный `pytest` + `git push origin master`) НЕ выполнены в рамках этого
> прохода — они вне выданного мандата, не забыты. Тесты прогнаны отдельно вне Шага 5
> (см. отчёт задачи 11): 235 passed, не 223, как ожидал этот шаг (223 — счётчик на
> момент написания плана, до Задач 4–6). Граф остаётся не пересобранным — открытый долг,
> граф-первый процесс работает по устаревшему графу, пока `/understand` не будет запущен.

**Files:**
- Modify: `README.md` (раздел «Ограничения»)
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-07-08-roadmap-next-steps.md`

- [x] **Шаг 1: Починить README**

Раздел «Ограничения» врёт после мержа. Убрать пункт «В `master` все карточки кадров и отрезков имеют `status: skeleton`… лежат в ветке `spike/provider-verification` и ещё не слиты» — заменить на актуальный список verified-моделей. Пункт про Runware («не проверен живьём») убрать после задачи 5. Пункт про звук и про ручной путь «бриф → shots.json» оставить — они всё ещё верны.

- [x] **Шаг 2: Дополнить CLAUDE.md**

Добавить в «Правила» пункт про `ensure_png` (кадры нормализуются в настоящий PNG после скачивания — расширение не врёт) и, если задача 8 закрыта отказом от нормализации, пункт про разрешение отрезков.

- [x] **Шаг 3: Отметить закрытые фазы в роадмапе**

В `2026-07-08-roadmap-next-steps.md` проставить статус по каждой фазе с датой закрытия и ссылкой на этот план. Не удалять текст фаз — роадмап читается как журнал.

- [ ] **Шаг 4: Пересобрать knowledge-graph**

```bash
/understand
```

Инкрементальный прогон подхватит новый `ensure_png`, изменённый `runware.py` и новый тест-файл. Граф — основа граф-первого процесса, устаревший граф хуже отсутствующего.

НЕ выполнено в этом проходе — вне мандата задачи 11 этой итерации (см. пометку статуса
выше). Остаётся долгом.

- [ ] **Шаг 5: Финальная проверка и пуш**

```bash
.\.venv\Scripts\python.exe -m pytest -q && git status --short && git push origin master
```

Ожидание: 223 passed, рабочее дерево чистое.

НЕ выполнено в этом проходе — push вне мандата задачи 11 этой итерации. Тесты 235
passed прогнаны отдельно (см. пометку статуса выше), рабочее дерево на момент запуска
было чистым, но после этой правки содержит незакоммиченные изменения в трёх файлах.

---

## Порядок и зависимости

```
Задача 1 (мёрж) ─── разблокирует ВСЁ
   │
   ├── Задача 2 (ops: ключи, баланс WaveSpeed, копия D:) ─── выполняет пользователь
   │        │
   │        ├──► Задача 4 → Задача 5   (Runware живьём; нужен только баланс Runware — уже есть)
   │        └──► Задача 6              (seedance ×2; ЖДЁТ пополнения WaveSpeed)
   │
   ├── Задача 3 (ensure_png)      ─┐
   ├── Задача 7 (дакинг)           ├─ бесплатны, ни от чего не зависят кроме мержа
   ├── Задача 8 (разрешение)       │
   └── Задача 9 (выводы по звуку) ─┘
             │
             ▼
       Задача 10 (brainstorming Фазы 4) → отдельный план
             │
             ▼
       Задача 11 (доки + граф) — последней, когда факты перестали меняться
```

Что кому нужно от пользователя: задача 2 целиком, шаг 1 задачи 7 (выбор варианта дакинга на слух), шаг 1 задачи 8 (решение по разрешению), шаг 1 задачи 9 (прослушивание проб), задача 10 (brainstorming).

## Что этот план сознательно НЕ закрывает

По решению пользователя от 2026-08-01 скоуп — «долги роадмапа + звук». Вне скоупа остаётся, и это остаётся долгом:

- **Этапы 1–5 базовой спеки** — скиллы `research` / `story` / `script` / `characters` / `storyboard`, каталог `.claude/skills/`, `bible/`, `research.md`, `script.md`, протокол трёх чекпоинтов, автогенерация `shots.json`. Путь «бриф → `shots.json`» остаётся ручным.
- **Три уровня защиты консистентности персонажей** (спека §7) — работает только передача `refs` в `shots.json`.
- **Пилот** (спека §14): мини-серия 60–90 сек, 2 персонажа, 12–18 отрезков. Пока не пройден, открытые вопросы §16 (реальный процент брака, стоимость серии, липсинк, нативный звук видеомоделей) остаются без ответа.
- **Шортс-баннер и 9:16 в сборке** — аспект считается, наложение баннера отложено.
