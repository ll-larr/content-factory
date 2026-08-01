---
id: flux_2_klein
type: image
family: flux
status: verified          # WaveSpeed подтверждён живьём 2026-07-08 (2 генерации, $0.01; с resolution_style:size — честные 1280x720 JPEG); Runware НЕ проверен — баланс пополнен 2026-08-01, но живой submit упал HTTP 400 missingDimensionParameters ДО создания задачи ($0 списано); адаптер не шлёт width/height для imageInference, см. runware-api.md
providers:
  wavespeed: { id: "wavespeed-ai/flux-2-klein-9b/text-to-image", resolution_style: size, pricing: flat, usd_per_image: 0.01 }  # реальный path; схема знает ТОЛЬКО size "W*H" (2026-07-08)
  runware:   { id: "runware:400@2", pricing: flat, usd_per_image: 0.008 }   # FLUX.2 [klein] 9B (modelSearch 2026-06-17); submit живьём 2026-08-01 отклонён missingDimensionParameters — цена НЕ подтверждена живой генерацией
---

# Flux 2 Klein — дёшево, стилизация/мультфильм

> Дефолт-кадр для типов `animated_*` (FINAL §4): дёшево, хорошо держит стиль
> мультфильма/аниме. model-id/AIR подтвердить первым боевым запуском.
