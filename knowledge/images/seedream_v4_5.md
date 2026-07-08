---
id: seedream_v4_5
type: image
family: seedream
status: verified          # WaveSpeed подтверждён живьём 2026-07-08 ($0.04, файл получен; без size вышел квадрат 2048x2048 — контракт size тот же, что у flux, живьём size-маппинг проверен на flux); OpenRouter НЕ проверен
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: []
cost_tier: unknown
providers:                # рабочая лошадка кадров, консистентность (FINAL §3.1): $0.04
  wavespeed:  { id: "bytedance/seedream-v4.5", resolution_style: size, pricing: flat, usd_per_image: 0.04 }  # схема знает ТОЛЬКО size "W*H" (2026-07-08)
  openrouter: { id: "bytedance/seedream-4.5",  pricing: flat, usd_per_image: 0.04 }
---

# Seedream 4.5 (seedream_v4_5) — рабочая лошадка кадров, консистентность

> Дефолт-кадр для `film`/`series` (FINAL §4). model-id под WaveSpeed/OpenRouter
> подтвердить первым боевым запуском.

> Примечание: в исходном плане упоминался seedream-4.0; актуальная доступная
> модель — `seedream_v4_5` (Seedream 4.5).

(карточка-скелет: параметры собрать на спайке; цена — в providers-блоке)

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
