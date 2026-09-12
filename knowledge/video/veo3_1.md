---
id: veo3_1
type: video
family: veo
status: catalog           # пути, сетка длительностей, поля и цены сверены по каталогу WaveSpeed 2026-09-04; ЖИВОЙ ГЕНЕРАЦИИ НЕ БЫЛО — решение тратить принято человеком 2026-09-04
supports_start_end_frame: true
native_audio: true
max_clip_seconds: 8
allowed_durations: [4, 6, 8]
aspect_ratios: ["16:9", "9:16"]
cost_tier: high
providers:
  wavespeed:
    supports_start_end: true
    max_clip_seconds: 8
    allowed_durations: [4, 6, 8]
    media: { start: image, end: last_image }   # у veo end-кадр называется last_image, не end_image
    pricing: flat                              # цена за ГЕНЕРАЦИЮ, не за секунду
    tiers:
      lite: { id: "google/veo3.1-lite/image-to-video", usd_per_image: 0.30 }
      lite_start_end: { id: "google/veo3.1-lite/start-end-to-video", usd_per_image: 0.40 }
      fast: { id: "google/veo3.1-fast/image-to-video", usd_per_image: 1.20 }
      pro:  { id: "google/veo3.1/image-to-video", usd_per_image: 3.20 }
    default_tier: lite
  openrouter:             # перенесено из карточки veo3_1_lite (удалена 2026-09-12): у OpenRouter это та же Veo 3.1 Lite, и вторая карточка на ту же модель давала в панели две строки об одном
    supports_start_end: true
    max_clip_seconds: 8
    allowed_durations: [4, 6, 8]
    pricing: flat
    id: "google/veo-3.1-lite"
    usd_per_sec: 0.03     # ПОДТВЕРЖДЕНО ЖИВЬЁМ 2026-06-17 (submit→poll→download, $0.12 за 4 с 720p); 1080p дороже — не замерено
---

# Google Veo 3.1 (veo3_1)

> **Карточка открыта БЕЗ живой генерации** — решение человека 2026-09-04. Всё
> ниже взято из каталога WaveSpeed (`GET /api/v3/models`, поле `api_schema`),
> а не подтверждено списанием. Первая же реальная генерация обязана сверить
> цену дельтой баланса и перевести карточку в `verified` с замеренным числом:
> каталог уже дважды ошибался на аудио — у `gemini_2_5_pro_tts` в 2.4 раза,
> у qwen3 вдвое.

## Цена — главное, что нужно знать

Цена за ГЕНЕРАЦИЮ, а не за секунду:

| Тир | Путь | Цена |
|---|---|---|
| `lite` | `google/veo3.1-lite/image-to-video` | $0.30 |
| `lite_start_end` | `google/veo3.1-lite/start-end-to-video` | $0.40 |
| `fast` | `google/veo3.1-fast/image-to-video` | $1.20 |
| `pro` | `google/veo3.1/image-to-video` | $3.20 |

Для сравнения: пилот снят на `vidu_q2_turbo` по $0.11 за отрезок. Тир `pro`
дороже в тридцать раз — минута серии из тринадцати отрезков стоит $41.60
против $1.43. Тир `lite` дороже втрое ($3.90 за серию), и это единственный
тир, который на нашем объёме осмыслен без отдельного разговора о бюджете.

## Сетка длительностей: 4, 6, 8 — пятёрки НЕТ

Это несовместимо с режимом `quality_mode: high`, который даёт отрезки по 5
секунд: `validate_video_model` отобьёт такой проект ДО трат сообщением
«duration 5s not in allowed grid [4, 6, 8]». Чтобы снимать на veo, проект
должен работать на отрезках 4, 6 или 8 секунд.

## Стык кадров

Вопреки прежней записи в этой карточке («end-кадр НЕ принимает», разведка
2026-06-12), схема каталога 2026-09-04 показывает поле `last_image` у тиров
`fast` и `pro`, а у `lite` — отдельный путь `start-end-to-video`. Имя поля
отличается от нашего умолчания (`end_image`), поэтому в блоке провайдера задан
`media: { start: image, end: last_image }`.

## Собственный звук

У `fast` и `pro` есть `generate_audio` со значением по умолчанию `true`. Это
значит, что выдача приходит СО ЗВУКОМ, а у нас звук свой: монтаж подключает
видео только с `muted` (правило репозитория), так что дорожка модели просто не
прозвучит. Отдельного действия не требуется, но помнить стоит — за неё платят.

## OpenRouter: та же Lite, но за секунду

Карточка `veo3_1_lite` слита сюда 2026-09-12: это была та же модель у другого
провайдера, и в панели она давала вторую строку об одном и том же. На
OpenRouter берут за СЕКУНДУ ($0.03/с, подтверждено живым прогоном 2026-06-17 —
$0.12 за 4 с 720p), то есть 4-секундный отрезок там вчетверо дешевле
WaveSpeed-тира `lite` ($0.30 за генерацию). Провайдер OpenRouter у этой
карточки означает ровно Lite — `fast` и `pro` там не заведены.

## Разрешение

`lite`: 720p, 1080p. `pro`: 720p, 1080p, 4k. По умолчанию у `pro` — 1080p, то
есть без явного `resolution` он снимет дороже нужного.
