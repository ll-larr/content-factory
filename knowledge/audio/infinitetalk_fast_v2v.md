---
id: infinitetalk_fast_v2v
type: audio
audio_kind: lipsync
family: infinitetalk
status: skeleton          # цена из каталога WaveSpeed ($0.075), живой генерацией НЕ подтверждена; пригодность для ПЛОСКОГО МУЛЬТФИЛЬМА не проверена
output_format: mp4
cost_tier: medium
providers:
  # ⚠️ Закомментировано до живой генерации — см. mirelo_sfx_16. Отдельный риск:
  # модели липсинка учены на человеческих лицах, а у нас плоская рисовка и
  # жестяная птица с неподвижным клювом. Первая проба должна быть на реплике,
  # где лицо человека видно крупно.
  # wavespeed: { id: "wavespeed-ai/infinitetalk-fast/video-to-video", usd_per_image: 0.075, fields: { video: video, audio: audio, prompt: prompt } }
---

# InfiniteTalk Fast (video-to-video) — липсинк по готовому отрезку

Вход — готовый отрезок и готовый голос, выход — новый файл с движением губ.
Стадия идёт ПОСЛЕ звука и пишет отдельный файл `NNN-lipsync.mp4`: исходный
отрезок не перезаписывается, чтобы неудачный липсинк не уничтожил оплаченное
видео.

## Альтернативы в том же классе цен

- `veed/lipsync-v2` — $0.075
- `wavespeed-ai/ltx-2.3/lipsync` — $0.1
