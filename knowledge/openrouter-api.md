# OpenRouter API (видео) — контракт

Источник правды для `scripts/factory/providers/openrouter.py`. Точные эндпоинты, имена
полей и model-slug живут ТОЛЬКО здесь и в адаптере (правило CLAUDE.md).

> ⚠️ Контракт собран по официальной документации (context7 `/websites/openrouter_ai`,
> 2026-06-15), без живого спайка. Только **видео** (Veo 3.1, Seedance, Wan); Vidu и
> генерации изображений на OpenRouter нет (FINAL §1). Цены подтвердить боевым запуском.

## Аутентификация
- Заголовок: `Authorization: Bearer ${OPENROUTER_API_KEY}` (ключ из env, не хардкодить).
- База: `https://openrouter.ai/api/v1/videos`.

## Сабмит задачи
`POST https://openrouter.ai/api/v1/videos`
```json
{
  "model": "google/veo-3.1-lite",
  "prompt": "...",
  "duration": 5,
  "resolution": "720p",
  "aspect_ratio": "16:9",
  "generate_audio": false,
  "frame_images": [
    { "type": "image_url", "image_url": { "url": "<start: URL | data-URI>" },
      "frame_type": "first_frame" },
    { "type": "image_url", "image_url": { "url": "<end: URL | data-URI>" },
      "frame_type": "last_frame" }
  ]
}
```
- model-slug (`google/veo-3.1`, `google/veo-3.1-lite`, `bytedance/seedance-2.0`,
  `alibaba/wan-2.7`) — в карточке как `providers.openrouter.id` / `…tiers.<tier>.id`.
- Референсы (reference-to-video) — `input_references: [{type:"image_url", image_url:{url}}]`.
- Ответ: `{ "id": "job-...", "polling_url": "/api/v1/videos/job-...", "status": "pending" }`
  → адаптер берёт `id`.

## Опрос результата
`GET https://openrouter.ai/api/v1/videos/<id>` (Bearer).
```json
{ "status": "completed", "unsigned_urls": ["https://.../out.mp4"] }
```
- `status`: `pending` / `processing` / `completed` / `failed` / `cancelled` / `expired`.
- `unsigned_urls[0]` — URL результата (фолбэк скачивания: `…/videos/<id>/content?index=0`
  с Bearer). Результат скачивается HTTP-ом.

## Цены (FINAL §3.2)
Множитель 1080p OpenRouter — **×2.25**. Сильные стороны: **Veo 3.1 Fast/full** (премиум-
реализм/UGC) и Seedance std. flat-модели (Veo/Kling) — цена от разрешения не зависит.
Базовые $/с и тип цены — в карточках (`providers.openrouter`); смета —
`models.estimate_media_cost`.

## Уточнения по докам (2026-06-16, context7)
- **Авторитетный список моделей+цен:** `GET https://openrouter.ai/api/v1/videos/models`
  (Bearer; это GET, генерации нет → трат нет). Возвращает на модель: `id`, `canonical_slug`,
  `supported_resolutions`, `supported_aspect_ratios`, `supported_durations`,
  `supported_frame_images` (`first_frame`/`last_frame`), `pricing_skus`
  (`per-video-second`, `per-video-second-1080p`). **Шаг 0 спайка OpenRouter — дёрнуть это и
  взять реальные id/цены/разрешения из него**, а не из догадок.
- Подтверждённые id: `google/veo-3.1`, `google/veo-3.1-lite`,
  **`bytedance/seedance-2.0-fast`** (карточка seedance_2_0 поправлена на этот id).
- ⚠️ **Seedance на OpenRouter — только 480p/720p** (1080p НЕ поддерживается); Veo —
  свои наборы разрешений. Сверять `supported_resolutions` по модели; цена 1080p берётся из
  `pricing_skus.per-video-second-1080p`, а не по формуле ×2.25, если SKU присутствует.
- `frame_images[].frame_type` = `first_frame`/`last_frame` ✓. Приём `data:`-URI в
  `image_url.url` вероятен, но докой явно не подтверждён — проверить на спайке.

## Подтверждено живьём 2026-06-17 (спайк, ключ задан)
- **`google/veo-3.1-lite` РАБОТАЕТ end-to-end:** submit→poll(`pending`→`completed`)→download.
  Ответ poll: `{id, status, unsigned_urls:[".../videos/<id>/content?index=0"], usage:{cost}}`.
  4с/720p без аудио = **$0.12** ($0.03/с — карточка поправлена, было $0.05). Файл — h264
  1280×720 4.0с. Длительности модели: **[4,6,8]** (НЕ 5/10).
- **⚠️ Скачивание требует Bearer:** `unsigned_urls` ведут на `api/v1/videos/<id>/content`
  и без `Authorization` дают **HTTP 401**. Адаптер: `OpenRouterProvider._download_file`
  переопределён (шлёт Bearer); CDN-ссылки WaveSpeed/Runware — без авторизации.
- **Реальные id (GET /api/v1/videos/models):** `kwaivgi/kling-v3.0-std`/`-pro` (не
  `kwaivgi/kling-3.0…`; OpenRouter Kling — **720p-only**, pro без аудио **$0.112/с**);
  `bytedance/seedance-1-5-pro` (Seedance 1.5 Pro есть на OpenRouter).
- **⚠️ Seedance на OpenRouter — токенная цена** (`video_tokens` $/токен), НЕ $/сек.
  Наш `estimate_media_cost` (flat/scaled) её не выражает — seedance_2_0.openrouter остаётся
  skeleton; нужна либо отдельная модель цены, либо брать Seedance у WaveSpeed/Runware.
