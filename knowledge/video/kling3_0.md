---
id: kling3_0
type: video
family: kling
status: verified          # WaveSpeed std подтверждён живьём 2026-07-08 (5с start+end_image, $0.42 сверено списанием, интерполяция ✓); pro/OpenRouter/Runware НЕ проверены
supports_start_end_frame: true
native_audio: true
max_clip_seconds: 10
aspect_ratios: ["16:9","9:16","1:1"]
cost_tier: medium
providers:                # flat: цена НЕ зависит от разрешения (FINAL §3.2) — дёшев на 1080p
  wavespeed:
    supports_start_end: true
    resolution_style: omit   # схема kling БЕЗ resolution/aspect_ratio (2026-07-08) — не слать, что шлёт конвейер
    pricing: flat
    tiers:
      std: { id: "kwaivgi/kling-v3.0-std/image-to-video", usd_per_sec: 0.084 }  # живьём 2026-07-08: end_image принят, $0.42/5с; формула каталога base*duration/5*(sound?1.5:1); duration 3..15; resolution НЕ слать (нет в схеме)
      # pro: { id: "kwaivgi/kling-v3.0-pro/image-to-video", usd_per_sec: 0.168 }  # ОТКЛЮЧЁН: id из каталога, цена — догадка (ровно 2x от std), живой генерацией не проверена
    default_tier: std
  # ⚠️ Блоки openrouter и runware ОТКЛЮЧЕНЫ (закомментированы) 2026-08-02, как и
  # тир pro выше. Причина та же, что у seedance_2_0: гейт трат КАРТОЧНОГО уровня —
  # validate_video_model смотрит общий status карточки, не на провайдера и не на тир.
  # Живой генерацией подтверждён ровно один маршрут: WaveSpeed std. Пока карточка
  # была skeleton, остальные никого не пускали; после verified они стали
  # «разрешёнными к тратам» с непроверенными ценами. Живые пробы уже дважды
  # показывали, что догадки по ценам врут в разы (seedance_2_0 занижал вдвое,
  # flux_2_klein завышал в 5x) — доверия к оставшимся догадкам это не добавляет.
  # Пока закомментировано: validate_video_model отдаёт «not available on provider»
  # (провайдер) или _concrete_id — «неизвестный tier» до сети (тир). Трат не будет.
  # Раскомментировать по одному, после живой генерации, вместе с фактической ценой.
  #
  # openrouter:             # models-list 2026-06-17: РЕАЛЬНЫЕ id; ⚠️ 720p-only; цена без аудио — живьём НЕ проверено
  #   supports_start_end: true
  #   pricing: flat
  #   tiers:
  #     std: { id: "kwaivgi/kling-v3.0-std", usd_per_sec: 0.084 }
  #     pro: { id: "kwaivgi/kling-v3.0-pro", usd_per_sec: 0.112 }
  #   default_tier: std
  # runware:                # AIR — ДОГАДКА (см. knowledge/runware-api.md: видели klingai:2@2 и klingai:kling@o1-standard, точный AIR 3.0 не подтверждён)
  #   supports_start_end: true
  #   pricing: flat
  #   tiers:
  #     std: { id: "klingai:kling@3.0-standard", usd_per_sec: 0.084 }
  #     pro: { id: "klingai:kling@3.0-pro", usd_per_sec: 0.168 }
  #   default_tier: std
---

# Kling v3.0 — реализм/сериал, flat-цена (дёшев на 1080p)

> Дефолт-финал 1080p для `film`/`series` (FINAL §4): flat-цена не растёт с разрешением,
> поэтому на 1080p дешевле scaled-Seedance. id/path под WaveSpeed/OpenRouter/Runware
> подтвердить первым боевым запуском.

> **Выбор внутри семейства Kling:** `kling2_6` НЕ принимает end-кадр (одно входное
> изображение), поэтому для схемы склейки отрезков непригодна. `kling3_0` принимает
> start+end кадры — кандидат по умолчанию для склейки отрезков (спека §4).

## Когда использовать

Кандидат по умолчанию для отрезков по start/end кадрам (спека §4): flat-цена не
растёт с разрешением (дёшев на 1080p) — оптимальный баланс среди моделей со start/end.
Цена — в providers-блоке (смета: `estimate_media_cost`, в $).

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

## Параметры (разведка 2026-06-12 — сверить с providers-блоком и docs провайдера на спайке)

- `prompt` — обязателен
- входные кадры: start + end (имена полей провайдера — в providers-блоке/адаптере)
- `duration` — integer, default `5`; доступно `5` и `10`
- `mode`/тир — `std` / `pro` (тиры в providers-блоке); резолюция до `4k`
- `aspect_ratio` — `16:9` / `9:16` / `1:1`
- **Start/end кадры:** поддержка подтверждена ✓
- Цена — в providers-блоке (смета: `estimate_media_cost`, в $).

## Звук

Модель умеет генерировать звук, но **для конвейера звук выключать** — аудио идёт
отдельной дорожкой (TTS/музыка/SFX — задача на ElevenLabs, стадия audio вынесена).

## Наблюдения раннего теста (reference, до мультипровайдерного спайка)

- **Start/end интерполяция работает**: первый кадр видео = start-кадр,
  последний = end-кадр; движение осмысленное, сцена и персонаж стабильны.
- Стиль кадров слегка «перерисовывается» под Kling (мягче контуры исходного
  flat 2D) — композиция и персонаж сохраняются.
- Фактические списания могут быть ниже сметы — сверять с дашбордом провайдера.
