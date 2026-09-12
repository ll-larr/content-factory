---
id: minimax_hailuo
type: video
family: hailuo
status: catalog           # путь, поля и цена сверены по каталогу WaveSpeed (GET /api/v3/models) 2026-09-12; ЖИВОЙ ГЕНЕРАЦИИ НЕ БЫЛО — решение тратить принято человеком 2026-09-12
supports_start_end_frame: true
native_audio: false
max_clip_seconds: 15
allowed_durations: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
aspect_ratios: []         # aspect_ratio в схеме ОТСУТСТВУЕТ (см. omit_aspect_ratio)
cost_tier: low
max_duration_sec: 15
providers:
  wavespeed:
    # Hailuo 3 (h3) — первая модель семейства со стыком кадров: `last_image`.
    # Линейка hailuo-2.3 end-кадра не знает вовсе и сюда не годится.
    supports_start_end: true
    media: { start: image, end: last_image }
    max_clip_seconds: 15
    allowed_durations: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    omit_aspect_ratio: true          # поля нет в схеме; `additionalProperties: false` → HTTP 400
    resolution_style: map            # сетка модели своя: 480p/540p/768p/1080p, 720p в ней НЕТ
    resolution_map: {720p: 768p, 1080p: 1080p}
    pricing: flat
    id: "wavespeed-ai/minimax-h3/image-to-video"
    usd_per_sec: 0.04
    # Цена: base_price каталога $0.20 за генерацию на дефолтных 5 с → $0.04/с
    # (та же арифметика, что сверена живьём у kling3_0). Путь minimax/h3 у того
    # же провайдера стоит $0.70 за те же 5 с — берём дешёвый.
    # Зависимость от разрешения НЕ замерена: на 1080p смета может занижать.
    # ПЕРВАЯ живая генерация обязана сверить дельтой баланса.
---

# Minimax Hailuo 3 / H3 (minimax_hailuo)

Стык кадров принимает (`last_image`), сетка длительностей свободная 3..15 —
в отличие от hailuo-2.3, где было 6/10 и одно входное изображение.

## Параметры (каталог WaveSpeed 2026-09-12)

- `image` + `last_image` — стартовый и (необязательно) конечный кадр
- `duration` — 3..15, по умолчанию 5
- `resolution` — `480p` / `540p` / `768p` / `1080p`; **720p нет**, поэтому
  карточка объявляет перевод 720p → 768p
- `aspect_ratio` — **поля нет**, отправка ломает запрос

## Сильные стороны

- $0.04/с со стыком кадров — дешевле seedance1_5 при свободной сетке секунд.

## Типовые ошибки

- Ждать ровно 1280×720: при 720p проекта модель снимает 768p, и файл будет
  выше. Внутри эпизода это одно и то же разрешение, между моделями — нет.
