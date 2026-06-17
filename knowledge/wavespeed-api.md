# WaveSpeed API — контракт

Источник правды для `scripts/factory/providers/wavespeed.py`. Точные эндпоинты, имена
полей и model-path живут ТОЛЬКО здесь и в адаптере (правило CLAUDE.md).

> ⚠️ Контракт собран по официальной документации (context7 `/websites/wavespeed_ai`,
> 2026-06-15), без живого спайка. Имена медиа-полей для start/end-кадров и точные
> 1080p-цены scaled-моделей подтвердить первым боевым запуском (FINAL оговорки).

## Аутентификация
- Заголовок: `Authorization: Bearer ${WAVESPEED_API_KEY}` (ключ из env, не хардкодить).
- База: `https://api.wavespeed.ai/api/v3`.

## Сабмит задачи
`POST https://api.wavespeed.ai/api/v3/<model-path>` — **model-path лежит в карточке**
как `providers.wavespeed.id` (или `…tiers.<tier>.id`), напр.:
- `bytedance/seedance-v2-fast/image-to-video`
- `vidu/q3/start-end-to-video`
- `kwaivgi/kling-v2.6-std/text-to-video`

Тело (JSON), нормализованные params → формат WaveSpeed (маппинг в адаптере):
```json
{
  "prompt": "...",
  "aspect_ratio": "16:9",
  "duration": 5,
  "resolution": "720p",
  "image": "<start: URL | data-URI>",
  "end_image": "<end: URL | data-URI>"
}
```
- Для image-моделей вместо `image`/`end_image` — массив `images` (референсы).
- Локальные файлы кодируются в `data:`-URI base64 (`BaseHTTPProvider._media`).

Ответ сабмита:
```json
{ "code": 200, "message": "success",
  "data": { "id": "task-abc123", "status": "created",
            "urls": { "get": "https://api.wavespeed.ai/api/v3/predictions/task-abc123/result" } } }
```
→ адаптер берёт `data.id`.

## Опрос результата
`GET https://api.wavespeed.ai/api/v3/predictions/<id>/result` (Bearer).
```json
{ "code": 200,
  "data": { "id": "task-abc123", "status": "completed",
            "outputs": ["https://cdn.../out.mp4"], "error": "" } }
```
- `data.status`: `created` / `processing` / `completed` / `failed`.
- `data.outputs[0]` — URL результата (пуст, пока не `completed`). Скачивается HTTP-ом.

## Цены (FINAL §3.2)
Множитель 1080p WaveSpeed — **×1.4** (офиц. блог). flat-модели (Kling/Veo/Wan 2.7) —
цена от разрешения не зависит. Базовые 720p $/с и `res_mult` хранятся в карточках
(`providers.wavespeed`), смета считается в `models.estimate_media_cost`.

## Два стиля API — ОБА поддержаны адаптером (2026-06-16, context7)
Стиль и имена медиа-полей задаются в карточке (`providers.wavespeed`), смены кода не требуют:

1. **v3 JSON** (по умолчанию): `POST api/v3/<path>`; кадры — строковые поля изображения
   (URL/data-URI base64 через `_media`). Имена полей настраиваются:
   ```yaml
   wavespeed:
     id: "vidu/start-end-to-video-q2-turbo"
     media: { start: start_frame, end: end_frame }   # дефолт image / end_image
   ```
2. **v1 multipart** (`api: v1_multipart`): `POST api/v1/<path>` с **загрузкой файлов**
   кадров (`start_frame=@`/`end_frame=@`); локальные пути обязательны (http/data-URI → ошибка):
   ```yaml
   wavespeed: { id: "vidu/turbo/start-end-to-video", api: v1_multipart,
                media: { start: start_frame, end: end_frame } }
   ```
   Кодировщик — `WaveSpeedProvider._encode_multipart`; poll/result — общий v3
   `predictions/<id>/result`.

**Vidu Q2 Turbo** доступен обоими путями: v3 `vidu/start-end-to-video-q2-turbo`
(параметры: `start_frame`,`end_frame` required, `prompt`,`duration` 1–10,
`resolution` 540p/720p/1080p, `movement_amplitude`, `bgm`, `seed`) ИЛИ v1-multipart
`vidu/turbo/start-end-to-video`. В карточке по умолчанию — v3 JSON.

### Сверить на спайке
- Точные имена полей кадров и приём data-URI в v3 JSON у конкретной модели.
- Ответ v1-multipart submit (предполагаем `{data:{id,urls.get}}`, как v3) и базовый URL
  v1 (`/api/v1` vs `/v1`, http vs https — в доке встречалось `http://api.wavespeed.ai/v1/...`).
- Путь Seedance 2.0 image/start-end (видели только `bytedance/seedance-2.0/video-edit-turbo`
  — это video-EDIT; в карточке догадка `bytedance/seedance-v2-fast/image-to-video`).
