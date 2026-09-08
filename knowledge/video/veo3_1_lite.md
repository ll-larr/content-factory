---
id: veo3_1_lite
type: video
family: veo
status: verified          # OpenRouter подтверждён живьём 2026-06-17 (submit→poll→download, $0.12/4с 720p)
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 8
aspect_ratios: []
cost_tier: medium
providers:                # flat; UGC/говорящая голова/lipsync (FINAL §4). OpenRouter — дом Veo.
  openrouter:             # models-list+живой тест 2026-06-17: frames first/last, 720p/1080p
    supports_start_end: true
    pricing: flat
    id: "google/veo-3.1-lite"
    usd_per_sec: 0.03     # 720p без аудио (подтверждено живьём); 1080p дороже
    allowed_durations: [4, 6, 8]   # ⚠️ НЕ 5/10 — для отрезков 5с не подойдёт
  # WaveSpeed-маппинг Veo был догадкой, не подтверждён — убран; добавить после спайка WS при необходимости
---

# Google Veo 3.1 Lite — UGC, lipsync, бюджет (flat)

> Дефолт-видео для `shorts`/UGC (FINAL §4). Премиум-вариант — Veo 3.1 full (OpenRouter).
> Точные model-slug/path и цену подтвердить первым боевым запуском.

## Параметры (разведка 2026-06-12 — сверить с providers-блоком и docs провайдера на спайке)

- **Start/end кадры:** поддержка подтверждена ✓
- Цена — в providers-блоке (смета: `estimate_media_cost`, в $).
- Остальные параметры (aspect_ratio, duration, resolution) — собрать на спайке.

**Ожидает живого спайка:** параметры, визуальное качество, интерполяция start→end.

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
