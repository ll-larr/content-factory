---
id: kling3_0
type: video
family: kling
status: skeleton          # модель проверена живьём на Higgsfield, но маппинг WS/RW/OR — нет
supports_start_end_frame: true
native_audio: true
max_clip_seconds: 10
aspect_ratios: ["16:9","9:16","1:1"]
cost_tier: medium
providers:                # flat: цена НЕ зависит от разрешения (FINAL §3.2) — дёшев на 1080p
  wavespeed:
    supports_start_end: true
    pricing: flat
    tiers:
      std: { id: "kwaivgi/kling-v3.0-std/start-end-to-video", usd_per_sec: 0.084 }
      pro: { id: "kwaivgi/kling-v3.0-pro/start-end-to-video", usd_per_sec: 0.168 }
    default_tier: std
  openrouter:
    supports_start_end: true
    pricing: flat
    tiers:
      std: { id: "kwaivgi/kling-3.0", usd_per_sec: 0.084 }
      pro: { id: "kwaivgi/kling-3.0-pro", usd_per_sec: 0.168 }
    default_tier: std
  runware:
    supports_start_end: true
    pricing: flat
    tiers:
      std: { id: "klingai:kling@3.0-standard", usd_per_sec: 0.084 }
      pro: { id: "klingai:kling@3.0-pro", usd_per_sec: 0.168 }
    default_tier: std
---

# Kling v3.0 — реализм/сериал, flat-цена (дёшев на 1080p)

> Дефолт-финал 1080p для `film`/`series` (FINAL §4): flat-цена не растёт с разрешением,
> поэтому на 1080p дешевле scaled-Seedance. id/path под WaveSpeed/OpenRouter/Runware
> подтвердить первым боевым запуском.

> **Замена спеки:** В плане фигурировала «Kling 2.0», однако Kling 2.0/2.1/2.5
> в CLI Higgsfield не существуют. Доступные Kling-модели: `kling2_6` и `kling3_0`.
> `kling2_6` не принимает end-кадр (проверено cost-валидацией 2026-06-12).
> `kling3_0` принимает `--start-image` + `--end-image` — кандидат по умолчанию для склейки отрезков.

## Когда использовать

Кандидат по умолчанию для отрезков по start/end кадрам (спека §4).
Цена 10 кредитов за 5с — оптимальный баланс цены и возможностей среди проверенных моделей со start/end.

## Структура промпта движения

Кадры уже задают композицию — промпт описывает **только движение**:

```
[что движется и как]
+ [движение камеры: static / slow push-in / pan left]
+ [темп]
```

Не переописывать сцену и персонажа — модель интерполирует между кадрами.

## Типовые ошибки

- Резкая смена композиции между start и end кадрами → рваная интерполяция.
- Слишком длинный промпт → модель игнорирует кадры и «выдумывает» сцену.

## Звук (native_audio)

Модель поддерживает генерацию звука (параметр `sound on/off`, default `on`).
**Для конвейера звук выключать** (`sound off`) — звук фаза 2, управляется отдельно.

## Проверено разведкой CLI (2026-06-12, без генерации)

**Параметры:**
- `prompt` — обязателен
- `medias` — массив входных изображений (флаги `--start-image` / `--end-image` / `--image`)
- `duration` — integer, default `5`; доступно `5` и `10`
- `mode` — `std` / `pro` / `4k`; default `std`
- `sound` — `on` / `off`; default `on`
- `aspect_ratio` — `16:9` / `9:16` / `1:1`

**Матрица start/end:** `--start-image` + `--end-image` приняты cost-валидацией ✓

**Смета:** 10 кредитов за 5с (mode std).

## Проверено генерацией (smoke 2026-06-12)

- **Start/end интерполяция работает**: первый кадр видео = start-image (кот стоит),
  последний = end-image (лапа на кнопке), движение руки осмысленное, сцена и
  персонаж стабильны (spike/kling3_verify.mp4, 5с, 1280×720, sound off).
- Стиль кадров слегка «перерисовывается» под Kling (мягче контуры исходного
  flat 2D) — композиция и персонаж сохраняются.
- **Фактическое списание 7.5 кр при смете 10** (starter-подписка): реальные
  списания могут быть НИЖЕ смет — сверять по `higgsfield account transactions`.
- В params ответа есть недокументированные поля (`cfg_scale: 0.5`,
  `multi_shots`, `enhance_prompt: false` и др.) — дефолты CLI.
