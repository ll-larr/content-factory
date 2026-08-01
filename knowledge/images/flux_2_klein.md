---
id: flux_2_klein
type: image
family: flux
status: verified          # WaveSpeed подтверждён живьём 2026-07-08 (2 генерации, $0.01; с resolution_style:size — честные 1280x720 JPEG); Runware подтверждён живьём 2026-08-01 (runware:400@2, width/height 1280x720 → файл 1280x720 MJPEG, $0.00169 по полю cost)
providers:
  wavespeed: { id: "wavespeed-ai/flux-2-klein-9b/text-to-image", resolution_style: size, pricing: flat, usd_per_image: 0.01 }  # реальный path; схема знает ТОЛЬКО size "W*H" (2026-07-08)
  runware:   { id: "runware:400@2", pricing: flat, usd_per_image: 0.0017 }   # FLUX.2 [klein] 9B (modelSearch 2026-06-17); живьём 2026-08-01: две генерации 1280x720 дали cost $0.00078 и $0.00169 — берём верхнюю границу наблюдённого, чтобы смета не занижала. Прежние $0.008 были догадкой — реальность в 5x дешевле
---

# Flux 2 Klein — дёшево, стилизация/мультфильм

> Дефолт-кадр для типов `animated_*` (FINAL §4): дёшево, хорошо держит стиль
> мультфильма/аниме. model-id/AIR подтвердить первым боевым запуском.
