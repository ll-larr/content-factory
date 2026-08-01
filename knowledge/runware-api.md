# Runware API — контракт

Источник правды для `scripts/factory/providers/runware.py`. Точные эндпоинт, taskType,
имена полей и AIR-id живут ТОЛЬКО здесь и в адаптере (правило CLAUDE.md).

> ✅ Контракт подтверждён живыми генерациями 2026-08-01 (image `flux_2_klein`,
> video `vidu_q2_turbo`) — см. разделы «Спайк 2026-08-01» ниже: там семантика `status`
> в `getResponse`, обязательные `width`/`height`, `deliveryMethod` и фактические цены.
> Изначально контракт был собран по официальной документации (context7
> `/websites/runware_ai`, 2026-06-15). **Что всё ещё НЕ подтверждено живьём:**
> 1080p-цены и сами 1080p-размеры (не замаплены, см. `_RESOLUTIONS`), а также
> Runware-маппинги карточек `kling3_0` и `seedance_2_0` (у последней блок `runware`
> закомментирован до живой проверки). У `seedance1_5` и `nano_banana_*`
> блока `runware` в карточках нет вовсе — маппинга не существует, есть только
> найденный ниже AIR `bytedance:seedance@1.5-pro`, в карточку не внесённый.

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

## Спайк 2026-06-17 (ключ задан) — РЕАЛЬНЫЕ AIR через modelSearch + статус
Свободный `taskType: modelSearch` (без генерации) вернул настоящие AIR — карточки поправлены:
- **FLUX.2 [klein] 9B** = `runware:400@2` (есть варианты 4B `…@4`, base `…@3/@5`, KV `…@6`,
  dev `runware:400@1`); flux_2_klein.runware поправлен.
- **Vidu Q2 Turbo** = `vidu:3@2` (Q3 `vidu:4@1`, Q3 Turbo `vidu:4@2`, Q2 Pro `vidu:3@1`);
  vidu_q2_turbo.runware поправлен.
- **Seedance**: `bytedance:seedance@2.0` (seedance_2_0 уже верно), `bytedance:seedance@2.0-fast`,
  **`bytedance:seedance@1.5-pro`** (реальный AIR для seedance1_5.runware).
- **⚠️ Баланс:** живой `imageInference` (FLUX.2 klein) отклонён с `insufficientCredits` —
  AIR/контракт приняты (id больше не «architectureId error»), но **аккаунт Runware без баланса**.
  Для генерации — пополнить кошелёк (my.runware.ai/wallet). До успешной генерации карточки
  Runware остаются `skeleton`; вопрос `resolution` vs `width/height` для image не дошёл до
  проверки (баланс отбил раньше) — сверить после пополнения.

## Спайк 2026-08-01 (баланс пополнен) — imageInference: submit отклонён на missingDimensionParameters

Живая проба `flux_2_klein` (`runware:400@2`, `spike/live_runware_image.py`, через
`RunwareProvider.submit` как есть — `params={"prompt": ..., "aspect_ratio": "16:9",
"resolution": "720p"}`). Смета посчиталась (`$0.0080`, из карточки), но сам HTTP-запрос
на сабмит отклонён **до создания задачи** — ответ содержит `"data": []`, задача не
заведена, `taskUUID` в ответе — это эхо запроса, не идентификатор созданной работы:

```json
{
  "data": [],
  "errors": [
    {
      "code": "missingDimensionParameters",
      "message": "Missing dimension parameters. Either width and height, or referenceImages must be provided.",
      "parameter": ["width", "height", "referenceImages"],
      "type": "integer|array",
      "documentation": "https://runware.ai/docs/image-inference/api-reference#request-width",
      "taskUUID": "e5ede41d-7bb3-4fff-8c81-884a9bc5902c"
    }
  ]
}
```

- **Подтверждено живьём:** `imageInference` требует `width`+`height` (integer) ИЛИ
  `referenceImages`; строку `resolution` (`"720p"`), которую сейчас шлёт
  `RunwareProvider.submit`, `imageInference` не принимает и не подставляет вместо
  размеров — поле просто игнорируется, задача не создаётся. Уточнение от 2026-06-16
  подозревало это только для части видео-моделей; теперь подтверждено, что для
  image-моделей это тем более обязательный параметр, а не запасной вариант. Открытый
  вопрос "resolution vs width/height" остаётся открытым как отдельная задача:
  `RunwareProvider.submit` нужно доработать, чтобы слать `width`/`height` для
  image-задач (aspect_ratio+resolution → конкретные px), это НЕ сделано в рамках
  этого спайка (изменение адаптера — предметная область соседней задачи, здесь
  зафиксирован только факт).
- **НЕ подтверждено:** задача не была создана (`data: []`, ошибка на этапе submit), то
  есть живой ответ `getResponse` для FLUX.2 klein так и не увидели — состав полей,
  значение `cost`, точная семантика `status` в успешном ответе всё ещё НЕ проверены
  живьём. Оговорка из шапки файла закрыта только частично: контракт ошибки submit для
  image прояснился, а happy-path `getResponse`/`cost`/`status` — по-прежнему по
  документации, без живого подтверждения.
- **Деньги:** $0 списано — Runware отклоняет запрос до создания задачи, счёт не
  выставляется (баланс, пополненный 2026-08-01, спайком не тронут).

## Спайк 2026-08-01 (продолжение) — happy-path закрыт, `deliveryMethod` обязателен

После добавления `width`/`height` сабмит проходит, но обнаружилась вторая причина, по
которой цикл `submit → wait → download` не работал: **`deliveryMethod` у Runware разный
по умолчанию для разных типов задач** — `sync` для `imageInference`, `async` для
`videoInference` (docs `platform/python`, `models/vidu-q2-turbo`). При `sync` результат
приходит ПРЯМО в ответ на сабмит, задача закрывается, и последующий `getResponse` по её
`taskUUID` не возвращает ничего — адаптер поллил до таймаута уже завершённую задачу.

Сырой сабмит `imageInference` без `deliveryMethod` (подтверждение sync-поведения):

```json
{"data":[{"taskType":"imageInference","imageUUID":"ea228e89-…","taskUUID":"4beb00c2-…",
          "cost":0.00078,"seed":1478706282,
          "imageURL":"https://im.runware.ai/image/os/…/ea228e89-….jpg"}]}
```

**Решение адаптера:** `RunwareProvider.submit` шлёт `"deliveryMethod": "async"` для обеих
задач — одна ветка кода вместо двух, ответ на сабмит становится подтверждением, результат
всегда забирается через `getResponse`.

### Подтверждённый happy-path `getResponse`

Image (`flux_2_klein` = `runware:400@2`, 1280x720):

```json
{"data":[{"taskUUID":"52f41967-…","taskType":"imageInference","status":"success",
          "imageUUID":"12e9befd-…","cost":0.00169,"seed":1390191274,
          "imageURL":"https://im.runware.ai/image/os/…/12e9befd-….jpg"}]}
```

Video (`vidu_q2_turbo` = `vidu:3@2`, 5с, 1280x720, `frameImages` first/last):

```json
{"data":[{"taskUUID":"f1ea033a-…","taskType":"videoInference","status":"success",
          "videoUUID":"36e2d791-…","cost":0.11,"seed":1259273673,
          "videoURL":"https://vm.runware.ai/video/os/…/36e2d791-….mp4"}]}
```

- **Семантика `status`:** `processing` — не готово (поле `progress` — проценты),
  `success` — терминальный успех, `error` — терминальный провал (плюс массив `errors`).
  Наш `_status` нормализует наличие `imageURL`/`videoURL` в `completed` и этим покрывает
  `success`; `error` попадает в `_FAILED` базового слоя.
- **`cost`** приходит в ответе при `includeCost: true` — это источник правды по цене,
  прозой в карточках он не дублируется.

### Ограничения размеров (подтверждено докой + живьём)

- `width`/`height` — целые, ОБЯЗАТЕЛЬНЫ и для image, и для video (строка `resolution`
  не принимается вообще). Альтернатива для image — `referenceImages`.
- FLUX.2 [klein] 9B: диапазон 128–2048, **шаг 16** (`runware.ai/docs/models/bfl-flux-2-klein-9b`).
  1280x720 валидно (оба кратны 16), файл вышел ровно 1280x720 MJPEG.
- Vidu Q2 Turbo: 1280x720 принято, но файл вернулся **1284x716** — модель подгоняет
  размеры под себя. Это нормально; жёстко полагаться на запрошенные px нельзя.
- **1080p намеренно не замаплен**: 1080 не кратно 16, валидной пары без искажения
  соотношения сторон нет, а видео-модели своих ограничений в доках не декларируют.
  Адаптер на незамапленном `resolution` падает явной ошибкой до сети, а не шлёт
  непроверенные px (`_RESOLUTIONS` в `scripts/factory/providers/runware.py`).

### Деньги

Некорректный сабмит (`missingDimensionParameters`) отклоняется ДО создания задачи и
**не тарифицируется** — подбирать параметры можно бесплатно. Платятся только реально
созданные задачи. Наблюдённые цены: image 1280x720 — $0.00078 и $0.00169 (две
генерации, разброс есть); video 5с 720p — $0.11.
