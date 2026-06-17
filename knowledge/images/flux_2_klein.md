---
id: flux_2_klein
type: image
family: flux
status: skeleton          # маппинг провайдеров не проверен живьём
providers:
  wavespeed: { id: "wavespeed-ai/flux-2-klein-9b/text-to-image", pricing: flat, usd_per_image: 0.01 }  # реальный path (/api/v3/models 2026-06-17)
  runware:   { id: "runware:400@2", pricing: flat, usd_per_image: 0.008 }   # FLUX.2 [klein] 9B (modelSearch 2026-06-17)
---

# Flux 2 Klein — дёшево, стилизация/мультфильм

> Дефолт-кадр для типов `animated_*` (FINAL §4): дёшево, хорошо держит стиль
> мультфильма/аниме. model-id/AIR подтвердить первым боевым запуском.
