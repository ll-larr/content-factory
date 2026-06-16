---
id: <model-id>           # стабильный id модели (не зависит от провайдера)
type: image | video
family: <nano-banana|kling|seedance|veo|grok|soul|seedream|wan|hailuo|vidu|pixverse|flux>
status: skeleton         # skeleton | verified (после живой проверки маппинга провайдера)
supports_start_end_frame: false   # legacy-фолбэк (provider=None); под провайдера — в providers.*
native_audio: false
max_clip_seconds: 0      # legacy-фолбэк
allowed_durations: []    # legacy-фолбэк сетки длительностей; [] = неизвестна
aspect_ratios: []
cost_tier: unknown       # low | medium | high
# --- Карта провайдеров (FINAL §5.5). Точные id/path — в адаптере и его knowledge-доке. ---
providers:
  wavespeed:                       # пример scaled-видео с тиром
    supports_start_end: true
    pricing: scaled                # scaled | flat
    res_mult: {720p: 1.0, 1080p: 1.4}    # ×1.4 WaveSpeed; ×2.25 OpenRouter/Runware
    tiers:
      fast: { id: "<wavespeed model-path>", usd_per_sec: 0.10 }   # база 720p
    default_tier: fast
  runware:                         # пример flat-видео (id+цена без тиров)
    supports_start_end: true
    pricing: flat
    id: "<air:model@ver>"
    usd_per_sec: 0.084
  # image-провайдер: pricing flat + usd_per_image (разрешение не влияет)
  # wavespeed: { id: "<path>", pricing: flat, usd_per_image: 0.005 }
---

<!--
Смета (models.estimate_media_cost):
  image / usd_per_image → плоско за изображение;
  video flat            → usd_per_sec × duration;
  video scaled          → usd_per_sec(720p) × duration × res_mult[resolution].
status: skeleton блокирует трату до живой проверки маппинга провайдера (generate_batch → код 2).
-->


# <Название модели>

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
