---
id: z_image_turbo
type: image
family: flux
status: verified          # WaveSpeed подтверждён живьём 2026-06-17 (z-image/turbo, $0.005, файл получен)
providers:
  wavespeed:              # максимально дёшево (FINAL §3.1): $0.005/изобр.
    id: "wavespeed-ai/z-image/turbo"   # реальный path из /api/v3/models (спайк 2026-06-17)
    resolution_style: size  # схема знает ТОЛЬКО size "W*H" (2026-07-08); спайк 06-17 давал квадрат 1024*1024 — aspect_ratio игнорировался
    pricing: flat
    usd_per_image: 0.005
---

# Z Image Turbo — максимально дёшево, черновые кадры (WaveSpeed)

> Дефолт-кадр для научпопа/черновиков (FINAL §4). Разрешение на цену не влияет.
> Для консистентности персонажа на финале — Seedream 4.5 / Nano Banana Pro.
