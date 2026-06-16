---
id: veo3_1_lite
type: video
family: veo
status: skeleton
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 0
aspect_ratios: []
cost_tier: medium
providers:                # flat ~$0.05/с; UGC/говорящая голова/lipsync (FINAL §4)
  openrouter:
    supports_start_end: true
    pricing: flat
    id: "google/veo-3.1-lite"
    usd_per_sec: 0.05
  wavespeed:
    supports_start_end: true
    pricing: flat
    id: "google/veo3.1-lite/image-to-video"
    usd_per_sec: 0.05
---

# Google Veo 3.1 Lite — UGC, lipsync, бюджет (flat)

> Дефолт-видео для `shorts`/UGC (FINAL §4). Премиум-вариант — Veo 3.1 full (OpenRouter).
> Точные model-slug/path и цену подтвердить первым боевым запуском.

## Проверено разведкой CLI (2026-06-12, без генерации)

**Матрица start/end:** `--start-image` + `--end-image` приняты cost-валидацией ✓

**Смета:** 8 кредитов → cost_tier medium.

Остальные параметры (aspect_ratio, duration, resolution) не собраны разведкой 2026-06-12.

**Ожидает спайка (Task 2):** параметры, визуальное качество, интерполяция start→end.

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
