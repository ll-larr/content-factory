---
id: vidu_q2_turbo
type: video
family: vidu
status: verified          # WaveSpeed подтверждён живьём 2026-07-08 (5с 720p start→end, $0.20, интерполяция ✓); Runware подтверждён живьём 2026-08-01 (vidu:3@2, width/height 1280x720 + frameImages first/last → файл 1284x716 h264, 5.125с, $0.11 по полю cost) — на Runware та же генерация вдвое дешевле
supports_start_end_frame: true
native_audio: false
providers:
  runware:                # Runware: дешевле всего (FINAL §3.2) $0.021/$0.047
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 2.25}
    id: "vidu:3@2"        # Vidu Q2 Turbo — реальный AIR (modelSearch 2026-06-17)
    usd_per_sec: 0.022    # живьём 2026-08-01: 5с 720p = $0.11 (cost), смета по прежним 0.021 давала $0.105 — расхождение 5%
  wavespeed:              # WaveSpeed v3 JSON: start-end-to-video-q2-turbo (живьём 2026-07-08)
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.875}   # по каталожной формуле: 375000/200000 при 5с
    id: "vidu/start-end-to-video-q2-turbo"
    media: { start: image, end: last_image }  # реальные поля из схемы /api/v3/models (2026-07-08); прежние start_frame/end_frame были догадкой
    usd_per_sec: 0.04     # НЕЛИНЕЙНО: реальная формула 720p = (duration-1)*$0.05 (5с = $0.20, сверено списанием 2026-07-08); 0.04/с точен ТОЛЬКО для 5с-отрезков конвейера
    # Альтернатива — загрузка файлов кадров: api: v1_multipart, id: "vidu/turbo/start-end-to-video"
---

# Vidu Q2 Turbo — мультфильм/аниме, бюджет (Runware и WaveSpeed)

> Дефолт видео для типов `animated_film`/`animated_series` (FINAL §4): дёшево, быстро,
> хорошая консистентность персонажа. Доступен на **Runware** (дешевле) и на **WaveSpeed**
> (v3 JSON `start-end-to-video-q2-turbo` с полями `start_frame`/`end_frame`, либо
> v1-multipart-загрузка). id/цены/имена полей подтвердить первым боевым запуском.

## Когда использовать
Мультфильм/аниме в объёме на 720p. Для качества/16с/звука — Vidu Q3 (WaveSpeed);
альтернатива для аниме — PixVerse V6.
