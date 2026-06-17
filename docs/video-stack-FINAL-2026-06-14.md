# ФИНАЛ: провайдеры, модели и смета для видео/фото-конвейера

> Дата: 2026-06-14. Хендофф-документ для интеграции бэкенда.
> Доказательная база и проверка цен — в `video-image-market-deep-analysis-2026-06-14.md`.
> Продукт: нативный выбор разрешения (720p/1080p), выбор модели для фото и видео
> (с подсказками на фронте), типы контента: **мультфильм, аниме, научпоп, фильм/сериал, UGC**.
> Все видео-модели ниже поддерживают **start/end frame (FLF)**, кроме явно помеченных.

---

## 1. Каких провайдеров подключать

**Ядро — 2 провайдера, закрывают всё:**

| Провайдер | Зачем | API |
|---|---|---|
| **WaveSpeed** | основной: реализм, научпоп, UGC, Vidu Q3, ВСЕ фото-модели; самые низкие $/с | OpenAI-совм. REST + SDK, $1 free |
| **Runware** | мультфильм/аниме бюджет (**Vidu Q2 Turbo**) + самые дешёвые фото + дешёвый fallback | 1 endpoint, async webhook/polling, $2 free |

**Опционально (3-й), если понадобится:**
- **OpenRouter** — единый ключ + **полная Veo 3.1** (премиум-реализм/UGC), нормализованный FLF. Нет Vidu.
- **fal** — лучший DX, но Seedance в 2–4× дороже; брать только за удобство.

Почему так: WaveSpeed+Runware дают все нужные модели с FLF по минимальной цене и с чистым
async-API под батч. Vidu (мультфильм/аниме) есть только у них (на OpenRouter Vidu нет).

---

## 2. Какие модели использовать

### Видео (с подсказками для фронта)
| Модель | Для чего (подсказка) | FLF | Цена-тип |
|---|---|---|---|
| **Vidu Q2 Turbo** | мультфильм/аниме, бюджет, консистентность персонажа | ✅ | scaled |
| **Vidu Q3** | мультфильм/аниме, качество (16с, multi-shot) | ✅ | scaled |
| **PixVerse V6** | аниме-специалист, дёшево, есть lipsync | ✅ | дёшево |
| **Wan 2.2 Ultra Fast** | научпоп/объём, абсолютный минимум цены | ✅ | scaled |
| **Seedance 2.0 (Fast)** | универсал: реализм + научпоп + 3D, хорош везде | ✅ | scaled |
| **Kling 3.0 Std** | реализм/сериал на **1080p** (flat, не дорожает!) | ✅ | flat |
| **Kling 3.0 Pro** | сериал-качество: люди, экшен, мульти-шот | ✅ | flat |
| **Veo 3.1 Lite/Fast** | UGC, говорящая голова, lipsync, дёшево | ✅ | flat |
| **Veo 3.1 full** | премиум-реализм/UGC (эталон, дорого) | ✅ | flat |

### Фото / ключевые кадры (с подсказками)
| Модель | Для чего | $/изобр. |
|---|---|---|
| **Z Image Turbo** | максимально дёшево, черновые кадры | $0.005 |
| **Flux 2 Klein** | дёшево, стилизация/мультфильм | $0.008 |
| **Seedream 4.5** | рабочая лошадка, консистентность | $0.04 |
| **Nano Banana 2** | качество, реалистичные кадры/лица | $0.07 |
| **Nano Banana Pro** | премиум-кадры 2K/4K, лица сериала | $0.14 |

---

## 3. Полная смета (отдельно фото, отдельно видео, сумма за секунду)

### 3.1 ФОТО — цена за изображение (разрешение почти не влияет)
| Модель | Провайдер | ~720p/1K | ~1080p/2K |
|---|---|---|---|
| Z Image Turbo | WaveSpeed | $0.005 | $0.005 |
| Flux 2 Klein | WaveSpeed | $0.008 | $0.008 |
| Seedream 4.5 | WaveSpeed/OpenRouter | $0.04 | $0.04 |
| Nano Banana 2 | WaveSpeed | $0.07 | $0.07 |
| FLUX.2 Pro | OpenRouter | $0.03 | $0.045 |
| Nano Banana Pro | WaveSpeed | — | $0.14 (2K) |
| (низ диапазона) | Runware | от $0.0006 | от $0.0013 |

### 3.1b Где какая модель дешевле — $/с по провайдерам (720p / 1080p)
> Множитель 1080p: **WaveSpeed ×1.4** (их офиц. блог), **OpenRouter/Runware ×2.25** (пиксельный закон).
> flat-модели (Kling, Veo, Wan 2.7) — цена не зависит от разрешения, одинакова у всех.

| Модель | OpenRouter | WaveSpeed | Runware | Дешевле |
|---|---|---|---|---|
| Seedance 2.0 Fast | $0.121 / $0.272 | **$0.10 / $0.14** | $0.13 / $0.29 | **WaveSpeed** |
| Seedance 2.0 std | $0.151 / $0.340 | только Fast | $0.16 / $0.36 | OpenRouter |
| Kling 3.0 Std (no audio) | $0.084 | $0.084 | $0.084 | ничья (flat) |
| Kling 3.0 Pro (audio) | $0.168 | $0.168 | $0.168 | ничья (flat) |
| Veo 3.1 Fast | **$0.08–0.10** | $0.15 | $0.15 | **OpenRouter** |
| Wan 2.2 Ultra Fast | — | **$0.01 / $0.014** | $0.021 / $0.047 | **WaveSpeed** |
| Wan 2.7 | $0.10 | $0.10 | $0.10 | ничья (flat) |
| Vidu Q2 Turbo | — | — | **$0.021 / $0.047** | **Runware** |
| Vidu Q3 | — | $0.07 / $0.10 | $0.07 / $0.16 | WaveSpeed |
| Фото (дешёвый кадр) | Seedream $0.04 | Z Image $0.005 | **от $0.0006** | **Runware** |

Вывод по провайдерам: **WaveSpeed** — Seedance Fast, Wan, Vidu Q3 (и выгоднее всех на 1080p);
**OpenRouter** — Veo Fast, Seedance std; **Runware** — Vidu Q2 Turbo + дешёвые кадры.

### 3.2 ВИДЕО — цена за секунду
> scaled: 1080p = 720p × **2.25** (OpenRouter/Runware) или × **1.4** (WaveSpeed); flat = одна цена.

| Модель / провайдер | Тип | 720p $/с | 1080p $/с |
|---|---|---|---|
| Vidu Q2 Turbo — Runware | scaled | $0.021 | $0.047 |
| Vidu Q3 — WaveSpeed | scaled | ~$0.07 | ~$0.15 |
| PixVerse V6 — WaveSpeed/fal | — | ~$0.01–0.10 | ~$0.02–0.20 |
| Wan 2.2 Ultra Fast — WaveSpeed | scaled | $0.01 | $0.023 |
| Seedance 2.0 Fast — WaveSpeed | scaled | $0.10 | $0.225 |
| Seedance 2.0 std — OpenRouter | scaled | $0.151 | $0.340 |
| **Kling 3.0 Std — WaveSpeed/fal** | **flat** | $0.084 | **$0.084** |
| Kling 3.0 Pro (audio on) | flat | $0.168 | $0.168 |
| Veo 3.1 Lite (+audio) | flat | $0.05 | ~$0.05 |
| Veo 3.1 Fast | flat | $0.08–0.10 | $0.08–0.10 |
| Veo 3.1 full | flat | ~$0.40 | ~$0.40 |

### 3.3 СУММА за секунду видео (видео + амортизированные кадры)
> Допущение: отрезки 10с → 1 новый кадр на ~10с видео = +0.1 кадра/с.
> Прибавка кадров копеечная (видно ниже) — итог ≈ цена видео.

| Тип контента | Видео $/с | + кадры $/с | **Итого $/с 720p** | **Итого $/с 1080p** |
|---|---|---|---|---|
| Мультфильм (Vidu Q2T + Flux Klein) | 0.021 / 0.047 | +0.0008 | **$0.022** | **$0.048** |
| Аниме (Vidu Q2T / PixVerse) | 0.021 / 0.047 | +0.0008 | **$0.022** | **$0.048** |
| Научпоп (Wan 2.2 UF + Z Image) | 0.01 / 0.023 | +0.0005 | **$0.011** | **$0.024** |
| Фильм/сериал (720p: Seedance Fast; 1080p: **Kling Std**) | 0.10 / 0.084 | +0.004 | **$0.104** | **$0.088** |
| UGC (Veo 3.1 Lite/Fast + NB2) | 0.05 / 0.10 | +0.007 | **$0.057** | **$0.107** |

**$/минуту (× 60):**
| Тип | 720p $/мин | 1080p $/мин |
|---|---|---|
| Мультфильм / Аниме | **$1.3** | $2.9 |
| Научпоп | **$0.7** | $1.4 |
| Фильм/сериал | $6.2 | **$5.3** |
| UGC | $3.4 | $6.4 |

> Примечание: на **1080p фильм/сериал ДЕШЕВЛЕ**, чем на 720p — потому что на 1080p
> переключаемся с scaled-Seedance на flat-Kling 3.0 Std. Это не опечатка, а суть стратегии.
> Добавь брак-фактор ×1.2–1.3 на регенерации при планировании бюджета.

---

## 4. Какой агрегатор и модели — по типам контента

| Тип контента | Провайдер | Видео-модель | Фото-модель | Итого $/с (720p → 1080p) |
|---|---|---|---|---|
| **Мультфильм** | **Runware** | Vidu Q2 Turbo (бюджет) / Vidu Q3 (качество) | Flux 2 Klein / Seedream | $0.022 → $0.048 |
| **Аниме** | **Runware** (дешевле на 720p) | Vidu Q2 Turbo ($0.021/с) / Vidu Q3; альт **PixVerse V6** | Flux 2 Klein / Seedream | $0.022 → $0.048 |
| **Научпоп** | **WaveSpeed** | Wan 2.2 Ultra Fast (объём) / Seedance 2.0 Fast (качество) | Z Image / Seedream | $0.011 → $0.024 |
| **Фильм/сериал** | **WaveSpeed** (+OpenRouter под Veo full) | 720p: Seedance 2.0 Fast · **1080p: Kling 3.0 Std**; качество: Kling 3.0 Pro / Veo 3.1 full | Seedream 4.5 / Nano Banana Pro | $0.104 → $0.088 |
| **UGC** | **WaveSpeed** / OpenRouter | Veo 3.1 Lite/Fast (бюджет) / Veo 3.1 full (премиум) | Nano Banana 2 | $0.057 → $0.107 |

### Логика для фронта (подсказки пользователю)
- **Мультфильм/Аниме** → Vidu (Q2 Turbo = дёшево/быстро, Q3 = качество/16с/звук). Аниме также: PixVerse V6.
- **Научпоп** → Wan 2.2 Ultra Fast (максимум объёма за минимум денег), Seedance 2.0 Fast (если нужна динамика).
- **Фильм/сериал** → 720p черновик на Seedance, 1080p-финал на Kling 3.0 Std (дёшево и нативно); премиум — Veo 3.1 full.
- **UGC** → Veo 3.1 (Lite для бюджета, full для рекламы) — лучший lipsync и реализм лица.
- **Разрешение:** 720p — для объёма/черновиков (scaled-модели дёшевы); 1080p — финал
  (для реализма переключай на flat-модели Kling/Veo, иначе scaled-Seedance дорожает ×2.25).

---

## 5. Что свести на бэкенде (привязано к реальной кодовой базе)

Опирается на текущие модули: `scripts/factory/higgsfield_client.py`, `models.py`,
`project.py`, `scripts/generate_batch.py`, карточки `knowledge/video|images/*.md`.

1. **Извлечь интерфейс провайдера из `higgsfield_client.py`.** Его публичная поверхность
   уже подходит — `estimate(model, params) -> float`, `submit(model, params) -> str`,
   `poll(job_id) -> dict`, `wait(...)`, `download(job_id, dest)`. Вынести в
   `scripts/factory/providers/base.py` (Protocol с этими методами); текущий клиент
   становится `providers/higgsfield.py` без смены поведения, тесты остаются зелёными.
2. **Новые адаптеры:** `providers/wavespeed.py`, `providers/runware.py`,
   опц. `providers/openrouter.py` — та же поверхность (`estimate/submit/poll/wait/download`).
   **Правило CLAUDE.md соблюсти:** точные эндпоинты/флаги каждого провайдера живут ТОЛЬКО
   в его адаптере и его knowledge-доке (как сейчас для Higgsfield — в
   `knowledge/higgsfield-cli.md` + `higgsfield_client.py`). Завести `knowledge/wavespeed-api.md`,
   `knowledge/runware-api.md`.
3. **Выбор провайдера через `project.json` → `Project`.** Сейчас `Project.models` —
   `dict[str,str]` с обязательными `image` и `video`. Добавить туда провайдера и тир,
   напр. `"video": {"model": "seedance", "provider": "wavespeed", "tier": "fast"}`
   (или плоские поля `video_provider`/`video_tier`) + новое поле **`resolution`** (`720p`/`1080p`).
   Фабрика `get_provider(name) -> VideoProvider` в `providers/__init__.py`.
4. **`generate_batch.py`:** заменить `from factory import higgsfield_client as hf`
   на `provider = get_provider(project.models["video"]["provider"])`; вызовы
   `hf.estimate/submit/poll/wait/download` → `provider.*`. Остальная логика (манифест,
   ревью, нумерация кадров) не меняется.
5. **Реестр моделей — расширить карточки `knowledge/` и `models.py`.** Сейчас
   `find_card(knowledge_dir, model_id)` + `validate_video_model(card, segment_seconds)`.
   В frontmatter карточки добавить карту провайдеров и тип цены:
   ```yaml
   model: seedance
   providers:
     wavespeed:  { id: "bytedance/seedance-2.0-fast", supports_start_end: true, pricing: scaled, res_mult: {720p: 1, 1080p: 1.4} }
     runware:    { id: "bytedance:seedance@2.0",        supports_start_end: true, pricing: scaled, res_mult: {720p: 1, 1080p: 2.25} }
     openrouter: { id: "bytedance/seedance-2.0",        supports_start_end: true, pricing: scaled, res_mult: {720p: 1, 1080p: 2.25} }
   ```
   `validate_video_model` дополнить проверкой `supports_start_end` и сетки длительностей
   ПОД ВЫБРАННОГО провайдера (для Kling/Veo `pricing: flat`).
6. **`estimate()` учитывает разрешение и тип цены.** Для `flat` — фикс $/с; для `scaled` —
   базовый 720p × `res_mult[resolution]` (×1.4 у WaveSpeed, ×2.25 у OpenRouter/Runware).
   Это держит смету на чекпоинте перед батчем точной (требование спеки §2).
7. **Дефолты по типу контента** из таблицы §4 (включая «аниме»): тип контента → провайдер+модель+тир,
   переопределяемые вручную в `project.json`.
8. Кадры — на дешёвой image-модели у того же провайдера; экономить на видео-разрешении, не на кадрах.

> Оговорки по достоверности: 720p-цены и flat-модели — проверены вживую/по формуле;
> 1080p у scaled-моделей WaveSpeed/Runware — по закону ×2.25 (подтверждён на fal+OpenRouter,
> их JS-прайс не парсится). PixVerse и Vidu Q3 точные $/с — сверить в плейбэке перед фиксацией.
