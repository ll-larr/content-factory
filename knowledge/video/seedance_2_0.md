---
id: seedance_2_0
type: video
family: seedance
status: skeleton          # маппинг провайдеров не проверен живьём — блокирует трату до спайка
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 10
aspect_ratios: ["auto","16:9","9:16","4:3","3:4","1:1","21:9"]
cost_tier: high
providers:
  wavespeed:              # Seedance 2.0 Fast — дешевле всех (FINAL §3.2): $0.10/$0.14
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.4}
    tiers:
      fast: { id: "bytedance/seedance-2.0-fast/image-to-video", usd_per_sec: 0.10 }  # реальный path (/api/v3/models 2026-06-17)
    default_tier: fast
  runware:                # $0.13/$0.29 (×2.25)
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 2.25}
    tiers:
      fast: { id: "bytedance:seedance@2.0", usd_per_sec: 0.13 }
    default_tier: fast
  openrouter:             # id ✓; ⚠️ только 480p/720p; ⚠️ цена ТОКЕННАЯ (video_tokens), usd_per_sec НЕВЕРНА — сверить
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 2.25}
    tiers:
      std: { id: "bytedance/seedance-2.0-fast", usd_per_sec: 0.151 }
    default_tier: std
---

# Seedance 2.0 — качественная видеомодель (универсал: реализм + научпоп + 3D)

> Провайдеры/цены — FINAL §3.2. Дефолт «фильм/сериал» на 720p (WaveSpeed Fast).
> Точные model-path/AIR-id и 1080p-цены подтвердить первым боевым запуском.

## Когда использовать

Дефолт high-quality-режима (спека §2):
- Лучше физика движения и стабильность персонажа по сравнению с kling3_0.
- Выдерживает более детальные описания вторичной анимации.

Дороже `kling3_0` (сравнить по providers-блокам обеих карточек / `estimate_media_cost`).
Использовать там, где качество критично, а не по умолчанию.

## Структура промпта движения

Кадры уже задают композицию — промпт описывает **только движение**:

```
[что движется и как]
+ [движение камеры: static / slow push-in / pan left]
+ [темп]
```

Выдерживает чуть более детальные описания движения
(вторичная анимация: хвост, ткань, волосы).

## Типовые ошибки

- Резкая смена композиции между start и end кадрами → рваная интерполяция.
- Слишком длинный промпт → модель игнорирует кадры и «выдумывает» сцену.
- На статичных планах (start ≈ end) добавлять micro-движение в промпт
  (`subtle idle sway`), иначе возможен «стоп-кадр».

## Параметры (разведка 2026-06-12 — сверить с providers-блоком и docs провайдера на спайке)

- `prompt` — обязателен
- входные кадры: start + end (имена полей провайдера — в providers-блоке/адаптере)
- `duration` — integer, default `5`
- тир — `std` / `fast` (в providers-блоке)
- `resolution` — `480p` / `720p` / `1080p`; default `720p` (⚠️ OpenRouter — без 1080p)
- `genre` — `auto` / `action` / `horror` / `comedy` / `noir` / `drama` / `epic`
- `aspect_ratio` — `auto`, `16:9`, `9:16`, `4:3`, `3:4`, `1:1`, `21:9`
- **Start/end кадры:** поддержка подтверждена ✓
- Цена — в providers-блоке (смета: `estimate_media_cost`, в $).

**Ожидает живого спайка:** реальная интерполяция start→end, визуальное качество,
сравнение с kling3_0 по стабильности персонажа.
