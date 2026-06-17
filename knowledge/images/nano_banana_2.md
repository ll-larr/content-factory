---
id: nano_banana_2
type: image
family: nano-banana
status: skeleton
supports_start_end_frame: false
native_audio: false
max_clip_seconds: 0
aspect_ratios: ["auto","1:1","3:2","2:3","4:3","3:4","4:5","5:4","9:16","16:9","21:9"]
cost_tier: medium
providers:                # Nano Banana Pro: премиум-кадры 2K/4K, лица сериала (FINAL §3.1): $0.14
  wavespeed: { id: "google/nano-banana-pro", pricing: flat, usd_per_image: 0.14 }
---

# Nano Banana Pro (nano_banana_2) — персонажи, текст, 4K

> Премиум-кадр (character sheets, читаемый текст) для `film`/`series` (FINAL §4).
> Бюджетный кадр UGC — Nano Banana 2 ($0.07). model-id WaveSpeed подтвердить спайком.

> **ЛОВУШКА ИМЁН:** id `nano_banana_2` — это **Nano Banana Pro**, НЕ Nano Banana 2.
> Настоящая Nano Banana 2 имеет id `nano_banana_flash`.
> Эта карточка описывает `nano_banana_2` = Nano Banana Pro.

## Когда использовать

- **Character sheets** (этап 5): листы персонажей с несколькими ракурсами.
- **Кадры с читаемым текстом** — вывески, баннеры шортсов, экраны устройств.
- **Ключевые кадры с максимальной детализацией** (default resolution 2k).

Дороже Nano Banana 2 (`nano_banana_flash`) — для массовой раскадровки не использовать.

## Структура промпта

```
[канонический блок персонажа — ДОСЛОВНО из bible/characters/*.md]
+ [действие в кадре]
+ [окружение]
+ [канонический блок стиля из style-guide.md]
+ [композиция/камера: wide shot / close-up / over-the-shoulder]
```

**Для character sheet:**
```
character sheet, front view / side view / back view / three-quarter view,
neutral pose, plain background
+ [канонический блок персонажа]
+ [канонический блок стиля]
```

Референсы передаются как изображения (имена полей — в providers-блоке/адаптере провайдера).

## Типовые ошибки

- Перегруз промпта деталями ломает композицию листа — один персонаж, один лист.

## Параметры (разведка 2026-06-12 — сверить с providers-блоком и docs провайдера на спайке)

- `prompt` — обязателен
- референс-изображения (имена полей провайдера — в providers-блоке/адаптере)
- `aspect_ratio` — `auto`, `1:1`, `3:2`, `2:3`, `4:3`, `3:4`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`; default `1:1`
- `resolution` — `1k` / `2k` / `4k`; default `2k`
- Цена — в providers-блоке (смета: `estimate_media_cost`, в $).

**Ожидает живого спайка:** визуальное качество, точность воспроизведения текста.
