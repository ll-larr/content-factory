# Runware API — контракт

Источник правды для `scripts/factory/providers/runware.py`. Точные эндпоинт, taskType,
имена полей и AIR-id живут ТОЛЬКО здесь и в адаптере (правило CLAUDE.md).

> ⚠️ Контракт собран по официальной документации (context7 `/websites/runware_ai`,
> 2026-06-15), без живого спайка. Семантику поля `status` в `getResponse` и точные
> 1080p-цены подтвердить первым боевым запуском (FINAL оговорки).

## Аутентификация
- Заголовок: `Authorization: Bearer ${RUNWARE_API_KEY}` (ключ из env, не хардкодить).
- Единый эндпоинт: `POST https://api.runware.ai/v1` — принимает **массив задач**.

## Сабмит задачи
```json
[
  {
    "taskType": "videoInference",
    "taskUUID": "<uuid4, генерим сами>",
    "model": "bytedance:seedance@2.0",
    "positivePrompt": "...",
    "duration": 5,
    "resolution": "720p",
    "includeCost": true,
    "inputs": {
      "frameImages": [
        { "image": "<start: URL | data-URI>", "frame": "first" },
        { "image": "<end: URL | data-URI>",   "frame": "last"  }
      ]
    }
  }
]
```
- AIR-id модели (`bytedance:seedance@2.0`, `klingai:kling@o1-standard`, `vidu:…`)
  лежит в карточке как `providers.runware.id` / `…tiers.<tier>.id`.
- Для image-моделей `taskType: "imageInference"`, без `duration`; референсы —
  `inputs.referenceImages`.
- `taskUUID` адаптер генерирует и возвращает как job_id.
- Ошибки сабмита → массив `errors` в ответе.

## Опрос результата
`POST https://api.runware.ai/v1` с `[{ "taskType": "getResponse", "taskUUID": "<id>" }]`.
Ответ:
```json
{ "data": [ { "taskUUID": "<id>", "videoURL": "https://vm.runware.ai/.../out.mp4",
              "cost": 0.1147 } ] }
```
- Готовность определяем по наличию `videoURL` / `imageURL` (нормализуем в `completed`).
- `errors` в ответе → `failed`. Результат скачивается HTTP-ом.

## Цены (FINAL §3.2)
Множитель 1080p Runware — **×2.25** (пиксельный закон). Самый дешёвый провайдер для
**Vidu Q2 Turbo** ($0.021/$0.047) и дешёвых кадров (от $0.0006). Базовые 720p $/с,
`res_mult` и тип цены — в карточках (`providers.runware`); смета —
`models.estimate_media_cost`.

## Уточнения по докам (2026-06-16, context7)
- **Формат изображения ПОДТВЕРЖДЁН:** `inputs.frameImages[].image` принимает
  **UUID / URL / Data-URI / Base64** (`^data:image/...;base64,...`). Значит `data:`-URI
  base64 из `BaseHTTPProvider._media` для Runware корректен — доработка не нужна.
- `frame` принимает `first` / `last` (а также индексы `0` / `-1`). Адаптер шлёт `first`/`last` ✓.
- Часть видео-моделей требует `width`/`height` (integer), а не строку `resolution`
  (пример Kling: `width/height/duration`). Сверить по конкретной модели на спайке —
  при необходимости адаптер должен слать width/height вместо/вместе с resolution.
- AIR-id Kling 3.0 уточнить (видели `klingai:2@2`, `klingai:kling@o1-standard`; в карточке —
  догадка `klingai:kling@3.0-standard/...`). Точные AIR — со страниц `runware.ai/docs/models/*`.
