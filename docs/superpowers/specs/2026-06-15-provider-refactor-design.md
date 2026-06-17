# ТЗ (адаптированное): мультипровайдерный видео/фото-конвейер без Higgsfield

> Дата: 2026-06-15. Адаптация исходного ТЗ «уйти от Higgsfield → WaveSpeed/Runware/OpenRouter»
> под подтверждённые решения. База знаний по моделям/ценам: `docs/video-stack-FINAL-2026-06-14.md`
> (далее «FINAL»). Этот документ — источник правды для рефактора; он НЕ теряет ничего из
> исходного ТЗ (см. §10 «Карта соответствия»), а уточняет его под новый стек.

Подтверждённые решения (отличия от исходного ТЗ):
- **Higgsfield вырезается полностью** (код + тесты + knowledge-док).
- Подключаются **три** провайдера: **WaveSpeed, Runware, OpenRouter**.
- Стадия **`storyboard` (кадры) переезжает на image-модель WaveSpeed/Runware**.
- Стадия **генерации `audio` отключается** (выносится в отдельную задачу — ElevenLabs).
  Сведение/сборка (`mix_audio`, `assemble`, `audio_plan`, `ffmpeg_tools`) — **остаются**.
- **Дефолт провайдера — по типу контента** (§5), переопределяется в `project.json`.

---

## 1. ЦЕЛЬ

Переписать слой генерации так, чтобы:
1. Higgsfield-провайдера в проекте не было вовсе.
2. Видео и кадры генерировались через **WaveSpeed / Runware / OpenRouter** за единым
   интерфейсом провайдера.
3. **Модель, провайдер, тир и разрешение** стали явными параметрами создаваемого
   контента (в `project.json`), с дефолтами по типу контента и ручным переопределением.
4. Смета (estimate) на чекпоинте перед батчем оставалась точной для 720p/1080p и для
   обоих типов цены (flat / scaled).

## 2. ЖЁСТКИЕ ОГРАНИЧЕНИЯ

- Скрипты запускаются **из корня репо** (пути `knowledge/`, `projects/` — относительные).
- Перед коммитом **`pytest -q` зелёный**. TDD по каждому этапу.
- **Правило изоляции провайдера (CLAUDE.md):** точные эндпоинты/флаги/`model-id` каждого
  провайдера живут ТОЛЬКО в его адаптере и его knowledge-доке. Завести:
  `knowledge/wavespeed-api.md`, `knowledge/runware-api.md`, `knowledge/openrouter-api.md`.
  Higgsfield-док (`knowledge/higgsfield-cli.md`) удаляется вместе с адаптером.
- **Ключи не хардкодить** — читать из env: `WAVESPEED_API_KEY`, `RUNWARE_API_KEY`,
  `OPENROUTER_API_KEY`. Реальные сетевые вызовы адаптеров **покрыть юнит-тестами через
  моки** (без живых запросов в CI).
- Реальные эндпоинты/пейлоады/`model-id` сверяются по официальным докам провайдеров
  (context7/firecrawl) и фиксируются в соответствующих knowledge-доках ПЕРЕД написанием
  адаптера.

## 3. ИНВАРИАНТЫ — что рефактор НЕ меняет (защита «изнутри»)

Эти свойства существующего конвейера сохраняются 1:1; их тесты остаются зелёными:

- **Смета бесплатна и идёт до трат.** Подтверждение сметы (`--yes` пропускает).
- **Валидация модели до трат** (`validate_video_model`) — supports start/end и сетка
  длительностей проверяются ПЕРЕД сабмитом; провал → код выхода 2, генерация не идёт.
- **Чекпоинт ревью:** `segments` строятся только на принятых кадрах (`done` /
  `accepted_with_notes`); иначе код 3.
- **Цикл отклонений:** `max_rejections`, автоперекуэуинг, `reject_count` не сбрасывается.
- **Resume:** застрявшие `generating` → `pending` на следующем прогоне.
- **Манифест** — формат, статусы, нумерация кадров/отрезков (`NNN`), `attempts`,
  `credits_spent`, `job_id` — без изменений (поле `credits_spent` переиспользуется под $).
- **shots.json / refs-резолвинг** — относительно папки проекта, без изменений.
- **Звук-сведение и сборка** (`mix_audio.py`, `assemble.py`, `audio_plan.py`,
  `ffmpeg_tools.py`, `knowledge/audio/*`, `validate_audio_model`) — без изменений.
- Коды выхода `generate_batch`: 0 успех; 1 сбои/отмена; 2 модель не прошла валидацию;
  3 segments заблокирован кадрами. (Код для отсутствующего audio.json уходит вместе со
  стадией audio.)

## 4. КАТАЛОГ ПРОВАЙДЕРОВ И МОДЕЛЕЙ (из FINAL §1–3)

**Провайдеры:** WaveSpeed (основной), Runware (мультфильм/аниме + дешёвые кадры),
OpenRouter (единый ключ, Veo 3.1, Seedance std; Vidu нет).

**Множитель 1080p:** WaveSpeed **×1.4**; OpenRouter/Runware **×2.25**; flat-модели —
цена от разрешения не зависит.

### Видео ($/с, 720p / 1080p)
| Модель | Провайдер(ы) | FLF | Цена | 720p | 1080p |
|---|---|---|---|---|---|
| Vidu Q2 Turbo | Runware | ✅ | scaled | $0.021 | $0.047 |
| Vidu Q3 | WaveSpeed | ✅ | scaled | ~$0.07 | ~$0.15 |
| PixVerse V6 | WaveSpeed | ✅ | scaled | ~$0.01–0.10 | ~$0.02–0.20 |
| Wan 2.2 Ultra Fast | WaveSpeed | ✅ | scaled | $0.01 | $0.023 |
| Seedance 2.0 Fast | WaveSpeed | ✅ | scaled | $0.10 | $0.225 (×2.25)/$0.14 (×1.4) |
| Seedance 2.0 std | OpenRouter | ✅ | scaled | $0.151 | $0.340 |
| Kling 3.0 Std | WaveSpeed/OpenRouter/Runware | ✅ | **flat** | $0.084 | $0.084 |
| Kling 3.0 Pro | WaveSpeed/OpenRouter/Runware | ✅ | **flat** | $0.168 | $0.168 |
| Veo 3.1 Lite | OpenRouter/WaveSpeed | ✅ | **flat** | ~$0.05 | ~$0.05 |
| Veo 3.1 Fast | OpenRouter | ✅ | **flat** | $0.08–0.10 | $0.08–0.10 |
| Veo 3.1 full | OpenRouter | ✅ | **flat** | ~$0.40 | ~$0.40 |

> Все модели выше поддерживают start/end frame (FLF). Точные $/с для PixVerse и Vidu Q3 —
> сверить в плейбэке перед фиксацией (оговорка FINAL §3.3/конца документа).

### Фото / ключевые кадры ($/изобр., разрешение почти не влияет)
| Модель | Провайдер | $/изобр. |
|---|---|---|
| Z Image Turbo | WaveSpeed | $0.005 |
| Flux 2 Klein | WaveSpeed | $0.008 |
| Seedream 4.5 | WaveSpeed/OpenRouter | $0.04 |
| Nano Banana 2 | WaveSpeed | $0.07 |
| Nano Banana Pro | WaveSpeed | $0.14 (2K) |
| FLUX.2 Pro | OpenRouter | $0.03 / $0.045 |
| (низ диапазона) | Runware | от $0.0006 |

## 5. ДЕФОЛТЫ ПО ТИПУ КОНТЕНТА (из FINAL §4)

Тип проекта (`project.type`) → дефолтный провайдер; переопределяется полем `provider`
в `project.json`. Модель и тир указываются в `project.json` (рекомендации — в таблице ниже).

| `project.type` | Категория FINAL | Дефолт-провайдер | Рекоменд. видео | Рекоменд. кадр |
|---|---|---|---|---|
| `animated_film`, `animated_series` | Мультфильм/Аниме | **runware** | Vidu Q2 Turbo / Vidu Q3 (аниме: PixVerse V6) | Flux 2 Klein / Seedream |
| `film`, `series` | Фильм/сериал | **wavespeed** | 720p: Seedance 2.0 Fast · 1080p: Kling 3.0 Std · премиум: Veo 3.1 full (OpenRouter) | Seedream 4.5 / Nano Banana Pro |
| `shorts` | UGC | **wavespeed** | Veo 3.1 Lite/Fast (премиум: full, OpenRouter) | Nano Banana 2 |

- **Провайдер кадров** по умолчанию = провайдер видео (тот же вендор; FINAL §5.8 —
  «экономить на разрешении видео, не на кадрах»).
- **Разрешение** по умолчанию `720p`; для реализма на 1080p рекомендуется переключение
  на flat-модели (Kling/Veo), иначе scaled дорожает (×1.4 / ×2.25).

## 6. СХЕМА `project.json`

`models.image` и `models.video` принимают **строку** (legacy: только `model-id`) ИЛИ
**объект** `{model, provider, tier}`. Плюс новое поле `resolution`.

```jsonc
{
  "name": "pilot",
  "type": "animated_series",
  "theme": "space cats",
  "resolution": "720p",                // "720p" | "1080p"; default "720p"
  "models": {
    "image": { "model": "flux_2_klein", "provider": "runware" },
    "video": { "model": "vidu_q2_turbo", "provider": "runware", "tier": "turbo" }
  }
}
```

Правила разбора (`project.py`):
- строка `"video": "vidu_q2_turbo"` → `{model, provider=дефолт-по-типу, tier=None}`;
- `provider` не задан → берётся дефолт по `type` (§5);
- `resolution` валидируется ∈ {`720p`,`1080p`} (читается top-level или `models.video.resolution`);
- свойства `Project`: `image_model/.image_provider/.video_model/.video_provider/.video_tier/.resolution`.

## 7. СХЕМА frontmatter карточки `knowledge/`

К существующему frontmatter добавляется карта `providers`. Существующие top-level поля
(`supports_start_end_frame`, `allowed_durations`, `max_clip_seconds`) сохраняются как
legacy-фолбэк для валидации без указания провайдера.

**Видео, scaled, с тирами:**
```yaml
id: seedance_2_0
type: video
providers:
  wavespeed:
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.4}
    tiers:
      fast: { id: "bytedance/seedance-2.0-fast", usd_per_sec: 0.10 }
    default_tier: fast
  openrouter:
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 2.25}
    tiers:
      std: { id: "bytedance/seedance-2.0", usd_per_sec: 0.151 }
    default_tier: std
```

**Видео, flat (Kling):**
```yaml
id: kling3_0
type: video
providers:
  wavespeed: { supports_start_end: true, pricing: flat,
               tiers: { std: {id: "...", usd_per_sec: 0.084},
                        pro: {id: "...", usd_per_sec: 0.168} },
               default_tier: std }
```

**Фото (flat per image):**
```yaml
id: z_image_turbo
type: image
providers:
  wavespeed: { id: "...", pricing: flat, usd_per_image: 0.005 }
```

Если тиров нет — допускается плоский `id` + `usd_per_sec`/`usd_per_image` на уровне провайдера.

## 8. ПЛАН ПО ЭТАПАМ (TDD, зелёный `pytest -q` после каждого)

### Этап A — интерфейс провайдера + удаление Higgsfield
- `+ scripts/factory/providers/base.py` — `Protocol VideoProvider`
  (`estimate(model, params)->float`, `submit(model, params)->str`, `poll(job_id)->dict`,
  `wait(...)`, `download(job_id, dest)->Path`, атрибут `unit`); базовое `ProviderError`.
- `+ scripts/factory/providers/__init__.py` — `get_provider(name)->VideoProvider`
  (`wavespeed`/`runware`/`openrouter`; неизвестный → `ProviderError`).
- `- scripts/factory/higgsfield_client.py`, `- tests/test_higgsfield_client.py`,
  `- knowledge/higgsfield-cli.md`.
- `~ CLAUDE.md` — заменить пункт про Higgsfield-флаги на правило per-provider изоляции.
- **Тесты:** `+ tests/test_providers.py` (фабрика, неизвестный провайдер → ошибка,
  `*Error` is-a `ProviderError`).

### Этап B — конфиг и реестр
- `~ scripts/factory/project.py` — dict/str для `models.image|video`, `provider`/`tier`,
  `resolution` + валидация, дефолты по типу, свойства доступа.
- `~ scripts/factory/models.py`:
  - `validate_video_model(card, segment_seconds, provider=None)` — при `provider`
    проверяет `providers[provider].supports_start_end` и сетку длительностей под него;
    без `provider` — legacy-поведение по top-level полям;
  - `+ estimate_media_cost(card, provider, resolution, duration_sec, tier=None)`:
    `flat = usd_per_sec×dur`; `scaled = usd_per_sec(720p)×dur×res_mult[resolution]`;
    `image = usd_per_image`.
- `~ knowledge/_template.md` и используемые видео/фото-карты — добавить `providers`-карту
  (числа из §4).
- **Тесты:** `~ test_project.py` (dict/str, провайдер-по-типу, resolution),
  `~ test_models.py` (provider-aware валидация; estimate flat / scaled 720p / 1080p ×1.4 /
  ×2.25 / image flat). Старые кейсы без provider остаются зелёными.

### Этап C — адаптеры и проводка
- `+ providers/wavespeed.py`, `+ providers/runware.py`, `+ providers/openrouter.py` —
  REST (async submit→poll→download на `urllib`), ключ из env, `unit="$"`, своё
  `*Error(ProviderError)`; маппинг нормализованных params
  (`start_frame/end_frame/refs/duration/aspect/resolution/tier`) → формат провайдера —
  ВНУТРИ адаптера; `estimate()` делегирует в `estimate_media_cost`.
- `+ knowledge/wavespeed-api.md`, `+ knowledge/runware-api.md`, `+ knowledge/openrouter-api.md`.
- `~ scripts/generate_batch.py`:
  - `storyboard` → `get_provider(project.image_provider)`;
  - `segments` → `get_provider(project.video_provider)` + `resolution` в params +
    `validate_video_model(card, seg, project.video_provider)`;
  - `except ProviderError`; смета печатается с `provider.unit`;
  - **удалить стадию `audio`** (build_jobs audio-ветка, `AUDIO_GROUPS`/`AUDIO_KINDS`,
    `_ext_from_url`, импорт `audio_plan`, аудио-валидация, `--stage audio`);
  - манифест/ревью/нумерация/resume — без изменений.
- `~ projects/_smoke/project.json` — привести к новой схеме (образец).
- **Тесты:** `+ tests/test_providers.py` (фабрика + три адаптера параметризованно:
  submit/poll/wait/download/estimate на моках, отсутствие ключа → ошибка — консолидировано
  в один файл вместо трёх); `~ test_generate_batch.py` (мок нового провайдера через
  `get_provider`, без audio, карты с `providers`, resolution).

## 9. ПРИЁМКА

- `pytest -q` зелёный (новый baseline без Higgsfield/audio-генерации).
- В кодовой базе **нет ссылок на higgsfield** (grep чист, кроме исторических docs/plans).
- Новый провайдер и модель выбираются через `project.json` **без правок кода**.
- `storyboard` идёт через image-провайдера; `segments` — через video-провайдера.
- Смета корректна для 720p и 1080p, для flat и scaled (юнит-тесты на `estimate_media_cost`).
- Все §3-инварианты сохранены (их тесты зелёные).

## 10. КАРТА СООТВЕТСТВИЯ: исходное ТЗ → адаптированное (ничего не потеряно)

| Пункт исходного ТЗ | Статус | Как реализовано здесь |
|---|---|---|
| Уйти от Higgsfield | ✅ усилено | Полный вырез (код+тесты+док), §8.A |
| Подключить WaveSpeed/Runware/OpenRouter | ✅ | §8.C, все три |
| Выбор модели/провайдера/тира/разрешения как параметров | ✅ | §6 схема `project.json` |
| Запуск из корня; `pytest -q` зелёный | ✅ сохранено | §2 |
| Изоляция эндпоинтов/флагов per-provider (CLAUDE.md) | ✅ сохранено | §2 + §8 (3 knowledge-дока) |
| Не хардкодить ключи; моки в CI | ✅ сохранено | §2 |
| Этап A: Protocol `VideoProvider`, `get_provider` | ✅ сохранено | §8.A |
| Этап A: «перенести клиент в higgsfield.py», back-compat импорта | ⚠️ ОТМЕНЕНО | Заменено полным вырезом (ваше решение). Поверхность интерфейса сохранена в `base.py` |
| «Higgsfield-поток не ломать (тесты без изменений)» | ⚠️ ПЕРЕНАЦЕЛЕНО | Higgsfield удалён; гарантия «не ломать изнутри» перенесена на §3 ИНВАРИАНТЫ (manifest/review/resume/shots/mix/assemble) |
| Этап B: `provider`/`tier`/`resolution` в `models.video` + валидация | ✅ | §6, §8.B; расширено и на `image` |
| Этап B: дефолт provider = higgsfield | ⚠️ ЗАМЕНЕНО | Дефолт по типу контента, §5 (higgsfield больше не существует) |
| Этап B: карта `providers` во frontmatter; `find_card`+`validate_video_model` под провайдера | ✅ | §7, §8.B |
| Этап C: адаптеры REST submit→poll→download | ✅ | §8.C |
| Этап C: `estimate()` flat=$/с, scaled=база720p×res_mult (×1.4 / ×2.25) | ✅ | §6/§8.B `estimate_media_cost` |
| Этап C: `generate_batch` hf.* → provider.*; манифест/ревью/нумерация не трогать | ✅ | §8.C, §3 |
| Приёмка: смета 720p/1080p flat+scaled | ✅ сохранено | §9 |
| (новое) image→WaveSpeed/Runware | ➕ добавлено | §5, §8.C |
| (новое) стадия audio off | ➕ добавлено | §8.C; сведение/сборка сохранены, §3 |
| (новое) каталог моделей и цен | ➕ добавлено | §4 |

## 11. Отложено / вне скоупа

- **Генерация звука** (TTS/music/sfx) — отдельной задачей (ElevenLabs). Стадия `audio`
  в `generate_batch` отключена; `audio_plan`/`mix_audio`/`assemble` сохранены под неё.
- **Авто-выбор модели по типу** (а не только провайдера) — опционально; пока модель
  указывается в `project.json`, провайдер/тир имеют дефолты по типу (§5).
- Точные $/с для PixVerse V6 и Vidu Q3, 1080p-цены scaled WaveSpeed/Runware — уточнить
  в плейбэке (оговорки FINAL).
