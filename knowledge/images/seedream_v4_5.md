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
  # ⚠️ Блок openrouter ОТКЛЮЧЁН 2026-08-02 (та же причина, что у seedance_2_0 и kling3_0):
  # гейт трат карточного уровня, verified по WaveSpeed открывал трату и на OpenRouter,
  # где id и цена живой генерацией не проверены. Закомментировано →
  # validate_image_model отдаёт «not available on provider», generate_batch exit 2.
  # Раскомментировать после живой генерации, вместе с фактической ценой.
  # openrouter: { id: "bytedance/seedream-4.5",  pricing: flat, usd_per_image: 0.04 }
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
