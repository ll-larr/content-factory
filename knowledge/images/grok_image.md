---
id: grok_image
type: image
family: grok
status: catalog           # путь, поля и цена сверены по каталогу WaveSpeed (GET /api/v3/models) 2026-09-12; ЖИВОЙ ГЕНЕРАЦИИ НЕ БЫЛО — решение тратить принято человеком 2026-09-12
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: ["1:1","16:9","9:16","4:3","3:4","3:2","2:3"]
cost_tier: low
supports_refs: false      # у text-to-image нет поля images: кадр по референсу персонажа этой моделью не сделать
providers:
  wavespeed:
    id: "x-ai/grok-imagine-image-v2.0/text-to-image"
    resolution_style: k   # схема знает 1k/2k; наши 720p/1080p переводятся таблицей адаптера
    pricing: flat
    usd_per_image: 0.05   # base_price каталога 2026-09-12; живым списанием НЕ сверено
---

# Grok Imagine Image 2.0 (grok_image)

Дешёвый кадр из текста. Референсы персонажей НЕ принимает: у `text-to-image`
нет поля `images`, а у `edit` (принимает ровно одну картинку) нет
`aspect_ratio` — для серии, где лицо держится референсом, модель не годится.
Её место — фоны, предметы, вставки без канона.

## Параметры (каталог WaveSpeed 2026-09-12)

- `prompt` — обязателен
- `resolution` — `1k` / `2k` (по умолчанию 2k); конвейерные 720p/1080p
  переводятся стилем `k`
- `aspect_ratio` — от `1:1` до `9:20`, по умолчанию `1:1`
- `quality` — `low` / `medium` (не отправляем, остаётся `medium`)

## Сильные стороны

- $0.05 за кадр 2k — вдвое дешевле nano_banana_2 при сопоставимом разрешении.

## Типовые ошибки

- Ставить в роль «Кадры» сериалу с персонажами: референс уехать не может,
  лицо поплывёт от кадра к кадру.
