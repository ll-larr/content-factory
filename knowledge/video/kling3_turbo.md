---
id: kling3_turbo
type: video
family: kling
status: catalog           # пути, поля и цены сверены по каталогу WaveSpeed (GET /api/v3/models) 2026-09-12; ЖИВОЙ ГЕНЕРАЦИИ НЕ БЫЛО — решение тратить принято человеком 2026-09-12
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 15
allowed_durations: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
aspect_ratios: []
cost_tier: low
max_duration_sec: 15
providers:
  wavespeed:
    # Отдельная карточка, а не тир kling3_0: turbo-ветка НЕ знает `end_image`
    # (в схеме его нет вовсе), а поддержка стыка объявляется на уровне
    # провайдера, не тира. Держать их в одной карточке значило бы обещать
    # стык там, где его нет.
    supports_start_end: false
    max_clip_seconds: 15
    allowed_durations: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    resolution_style: omit   # в схеме нет ни resolution, ни aspect_ratio
    pricing: flat
    tiers:
      std: { id: "kwaivgi/kling-v3-turbo-std/image-to-video", usd_per_sec: 0.0224 }
      pro: { id: "kwaivgi/kling-v3-turbo-pro/image-to-video", usd_per_sec: 0.028 }
    default_tier: std
    # Цена: base_price каталога $0.112 (std) и $0.14 (pro) за генерацию на
    # дефолтных 5 с → делим на 5. У kling3_0 ровно эта арифметика сверена живым
    # списанием ($0.42 за 5 с при base 0.42), поэтому перенос считаем
    # обоснованным — но ПЕРВАЯ живая генерация обязана сверить дельтой баланса.
---

# Kling 3 Turbo (kling3_turbo)

Вчетверо дешевле `kling3_0` std при том же семействе: $0.112 против $0.42 за
пятисекундный отрезок. Платится за это стыком кадров — его у turbo нет.

## Параметры (каталог WaveSpeed 2026-09-12)

- `image` — входной кадр, `prompt`, `cfg_scale`, `multi_prompt`
- `duration` — 3..15, по умолчанию 5
- ни `resolution`, ни `aspect_ratio`, ни `end_image` в схеме нет

## Сильные стороны

- Самая дешёвая kling: сериал из отрезков без стыков собирается вчетверо дешевле.

## Типовые ошибки

- Планировать стык планов: `end_frame` на этой модели отобьёт гейт платной стадии.
