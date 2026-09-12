---
id: grok_video_v15
type: video
family: grok
status: catalog           # пути, поля и цены сверены по каталогу WaveSpeed (GET /api/v3/models) 2026-09-12; ЖИВОЙ ГЕНЕРАЦИИ НЕ БЫЛО — решение тратить принято человеком 2026-09-12
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 15
allowed_durations: []     # duration — integer 1..15 без enum, сетки нет
aspect_ratios: []         # aspect_ratio в схеме ОТСУТСТВУЕТ (см. omit_aspect_ratio)
cost_tier: low
max_duration_sec: 15      # схема: duration min 1, max 15
providers:
  wavespeed:
    # Стыка кадров НЕТ: в схеме только `image`, поля end/last нет вовсе. Это не
    # запрет на модель — `end_frame` необязателен с 2026-09-03, — но план со
    # стыками на ней откажет гейтом платной стадии.
    supports_start_end: false
    max_clip_seconds: 15
    # aspect_ratio в схеме нет, а `additionalProperties: false` превращает лишнее
    # поле в HTTP 400. Кадр и так задаёт кадрирование — выбрасываем.
    omit_aspect_ratio: true
    # resolution в схеме есть и знает ровно наши значения (480p/720p/1080p) —
    # переводить нечего, шлём как есть.
    pricing: flat
    tiers:
      i2v: { id: "x-ai/grok-imagine-video-v1.5/image-to-video", usd_per_sec: 0.018 }
      t2v: { id: "x-ai/grok-imagine-video-v1.5/text-to-video",  usd_per_sec: 0.016 }
    default_tier: i2v
    # Цена: каталог отдаёт base_price за генерацию на дефолтных параметрах
    # ($0.09 i2v, $0.08 t2v). Пересчёт в секунду сделан делением на 5, как у
    # kling3_0, где та же арифметика сверена живым списанием. На 5-секундном
    # отрезке конвейера это даёт ровно каталожные $0.09. Зависимость цены от
    # разрешения НЕИЗВЕСТНА (res_mult нет): на 1080p смета может занижать.
    # ПЕРВАЯ живая генерация обязана сверить дельтой баланса и перевести
    # карточку в verified с замеренным числом.
---

# Grok Imagine Video 1.5 (grok_video_v15)

Дёшево и быстро оживляет ОДИН кадр. Требует входное изображение — у `t2v` его
нет, но конвейер всегда отдаёт `start_frame`, поэтому дефолтный тир — `i2v`.

## Параметры (каталог WaveSpeed 2026-09-12)

- `image` — входной кадр (обязателен у `i2v`), `prompt` — обязателен
- `duration` — целое 1..15, по умолчанию 6
- `resolution` — `480p` / `720p` / `1080p`, по умолчанию 720p
- `aspect_ratio` — **поля нет**, отправка ломает запрос (`additionalProperties: false`)
- end-кадра нет: стык планов делает монтаж, не модель

## Сильные стороны

- Самая дешёвая из открытых видеомоделей: ~$0.09 за 5-секундный отрезок.
- Сетка длительностей свободная (1..15), а не 5/10 — подходит под любой
  `segment_seconds` проекта.

## Типовые ошибки

- Ждать стыка кадров: `end_frame` в плане на этой модели отобьёт гейт.
- Считать цену линейной по разрешению: множитель 1080p не замерен.
