---
id: grok_video_v15
type: video
family: grok
status: skeleton          # реальные пути и цены каталога WaveSpeed сверены 2026-09-04, но живой генерации НЕ было
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: []
cost_tier: low
providers:
  # ⚠️ Закомментировано до живой генерации: гейт трат карточного уровня не должен
  # открывать трату на неподтверждённой цене. Цены — из GET /api/v3/models
  # (каталог WaveSpeed, 2026-09-04); каталог уже дважды ошибался на аудио —
  # у gemini в 2.4 раза, у qwen3 вдвое. Цена за ГЕНЕРАЦИЮ, не за секунду.
  # wavespeed:
  #   tiers:
  #     i2v: { id: "x-ai/grok-imagine-video-v1.5/image-to-video", usd_per_image: 0.09 }
  #     t2v: { id: "x-ai/grok-imagine-video-v1.5/text-to-video",  usd_per_image: 0.08 }
  #     ref: { id: "x-ai/grok-imagine-video-v1.5/reference-to-video", usd_per_image: 0.09 }
  #   default_tier: i2v
---

# Grok Video 1.5 (grok_video_v15)

Требует входное изображение — text-to-video недоступен (проверено разведкой 2026-06-12).

Поддержка start/end и остальные параметры — собрать на спайке.

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
