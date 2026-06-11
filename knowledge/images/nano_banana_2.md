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
---

# Nano Banana Pro (nano_banana_2) — персонажи, текст, 4K

> **ЛОВУШКА ИМЁН:** В CLI Higgsfield id `nano_banana_2` — это **Nano Banana Pro**, НЕ Nano Banana 2.
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

Референсы — параметр `input_images` (флаг CLI `--image`).

## Типовые ошибки

- Перегруз промпта деталями ломает композицию листа — один персонаж, один лист.

## Проверено разведкой CLI (2026-06-12, без генерации)

**Параметры:**
- `prompt` — обязателен
- `input_images` — массив референс-изображений (флаг CLI `--image`)
- `aspect_ratio` — enum: `auto`, `1:1`, `3:2`, `2:3`, `4:3`, `3:4`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`; default `1:1`
- `resolution` — `1k` / `2k` / `4k`; default `2k`
- `folder_id` — опциональный идентификатор папки

**Смета:** 2 кредита за картинку.

**Ожидает спайка (Task 2):** визуальное качество, точность воспроизведения текста.
