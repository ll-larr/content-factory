---
id: mirelo_sfx_16
type: audio
audio_kind: sfx
family: mirelo
status: verified          # подтверждено живьём 2026-09-05: цена ЗА СЕКУНДУ, не за генерацию — две пробы дельтой баланса дали ровно $0.01/с (1с → $0.0100, 5с → $0.0500)
output_format: mp3
cost_tier: low
providers:
  # Каталог WaveSpeed печатает base_price 0.01 — это цена ЗА СЕКУНДУ, а не за
  # генерацию, и прочтение её как плоской занизило смету эпизода впятеро
  # (2026-09-05: 78 секунд эффектов обошлись в $0.78 при смете $0.05).
  # Замер: 1с → $0.0100, 5с → $0.0500, ровно линейно.
  wavespeed: { id: "mirelo-ai/sfx-1.6/text-to-audio", pricing: flat, usd_per_sec: 0.01, fields: { prompt: text_prompt, duration: duration, ambience: ambience } }
---

# Mirelo SFX 1.6 — звуковые эффекты по описанию

Кандидат на роль SFX: выделенной модели эффектов на Runware нет вовсе
(`modelSearch` 2026-09-04 по foley/sound effects/video-to-audio — пусто).

## Структура запроса

```
text_prompt = "<описание эффекта>"
duration    = <секунды, по умолчанию 10>
ambience    = true    # для непрерывной подложки: результат сшивается в бесшовную петлю
```

`ambience: true` — то, что нужно для длинных подложек (море, ветер): модель
делает зацикливаемый кусок, а не одиночный звук с хвостом.
