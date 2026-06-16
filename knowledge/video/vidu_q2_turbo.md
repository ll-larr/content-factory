---
id: vidu_q2_turbo
type: video
family: vidu
status: skeleton          # маппинг провайдера не проверен живьём — блокирует трату до спайка
supports_start_end_frame: true
native_audio: false
providers:
  runware:                # Runware: дешевле всего (FINAL §3.2) $0.021/$0.047
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 2.25}
    id: "vidu:q2-turbo"   # AIR-id подтвердить спайком
    usd_per_sec: 0.021
  wavespeed:              # WaveSpeed v3 JSON: start-end-to-video-q2-turbo (поля start_frame/end_frame)
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.4}
    id: "vidu/start-end-to-video-q2-turbo"
    media: { start: start_frame, end: end_frame }
    usd_per_sec: 0.021    # цену WaveSpeed Vidu Q2T сверить (FINAL подтверждал только Runware)
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
