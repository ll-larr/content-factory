---
id: kling2_6
type: video
family: kling
status: skeleton
supports_start_end_frame: false
native_audio: true
max_clip_seconds: 10
aspect_ratios: ["16:9","9:16","1:1"]
cost_tier: medium
---

# Kling 2.6 Video (kling2_6)

End-кадр НЕ принимает (проверено 2026-06-12: CLI ответил «Model accepts a single image input» на `--start-image`+`--end-image`) — для схемы склейки отрезков непригодна.

## Проверено разведкой CLI (2026-06-12, без генерации)

**Параметры:**
- `input_image` — одно входное изображение (одиночный, не массив)
- `duration` — enum `"5"` / `"10"`
- `sound` — boolean, default `true` → `native_audio: true`
- `aspect_ratio` — `16:9` / `9:16` / `1:1`

**Смета:** 10 кредитов за 5с.

**Ожидает спайка (Task 2):** визуальное качество, применимость для планов без end-кадра.

## Сильные стороны
(карточка-скелет: наполняется при первом использовании модели)

## Структура промпта
(карточка-скелет: наполняется при первом использовании модели)

## Типовые ошибки
(карточка-скелет: наполняется при первом использовании модели)
