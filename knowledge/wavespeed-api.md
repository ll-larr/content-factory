# WaveSpeed API — контракт

Источник правды для `scripts/factory/providers/wavespeed.py`. Точные эндпоинты, имена
полей и model-path живут ТОЛЬКО здесь и в адаптере (правило CLAUDE.md).

> ⚠️ Контракт собран по официальной документации (context7 `/websites/wavespeed_ai`,
> 2026-06-15) и **частично подтверждён живыми генерациями**: Vidu Q2 Turbo 2026-07-08,
> Seedance 1.5 Pro и Seedance 2.0 Fast 2026-08-01 — все три по v3 JSON. Не подтверждено
> живьём: 1080p-цены scaled-моделей и путь v1-multipart (см. «Сверить на спайке» ниже).

## Аутентификация
- Заголовок: `Authorization: Bearer ${WAVESPEED_API_KEY}` (ключ из env, не хардкодить).
- База: `https://api.wavespeed.ai/api/v3`.

## Сабмит задачи
`POST https://api.wavespeed.ai/api/v3/<model-path>` — **model-path лежит в карточке**
как `providers.wavespeed.id` (или `…tiers.<tier>.id`), напр.:
- `bytedance/seedance-v2-fast/image-to-video`
- `vidu/q3/start-end-to-video`
- `kwaivgi/kling-v2.6-std/text-to-video`

Тело (JSON), нормализованные params → формат WaveSpeed (маппинг в адаптере):
```json
{
  "prompt": "...",
  "aspect_ratio": "16:9",
  "duration": 5,
  "resolution": "720p",
  "image": "<start: URL | data-URI>",
  "end_image": "<end: URL | data-URI>"
}
```
- Для image-моделей вместо `image`/`end_image` — массив `images` (референсы).
- Локальные файлы кодируются в `data:`-URI base64 (`BaseHTTPProvider._media`).

Ответ сабмита:
```json
{ "code": 200, "message": "success",
  "data": { "id": "task-abc123", "status": "created",
            "urls": { "get": "https://api.wavespeed.ai/api/v3/predictions/task-abc123/result" } } }
```
→ адаптер берёт `data.id`.

## Опрос результата
`GET https://api.wavespeed.ai/api/v3/predictions/<id>/result` (Bearer).
```json
{ "code": 200,
  "data": { "id": "task-abc123", "status": "completed",
            "outputs": ["https://cdn.../out.mp4"], "error": "" } }
```
- `data.status`: `created` / `processing` / `completed` / `failed`.
- `data.outputs[0]` — URL результата (пуст, пока не `completed`). Скачивается HTTP-ом.

## Баланс счёта

```
GET /api/v3/balance
```

Бесплатный запрос, подтверждён живьём 2026-09-04 (вернул 200 и $1.97). Число
приходит в `data.balance`; адаптер терпит и плоскую форму `{"balance": ...}` на
верхнем уровне, потому что схема снята одним живым вызовом и может отличаться
между версиями API. Отсутствие числа — ошибка, а не ноль: ноль на экране панели
означал бы «денег нет», хотя мы просто не смогли спросить.

Тем же бесплатным способом узнаются ЦЕНЫ: `GET /api/v3/models` отдаёт 1011 моделей
с полем `base_price` и полной схемой запроса. Догадки и пробные генерации ради
цены не нужны — но каталог врёт (у `gemini_2_5_pro_tts` в 2.4 раза), поэтому в
карточках стоят числа, замеренные дельтой баланса.

## Цены (FINAL §3.2)
Множитель 1080p WaveSpeed — **×1.4** (офиц. блог). flat-модели (Kling/Veo/Wan 2.7) —
цена от разрешения не зависит. Базовые 720p $/с и `res_mult` хранятся в карточках
(`providers.wavespeed`), смета считается в `models.estimate_media_cost`.

## Два стиля API — ОБА поддержаны адаптером (2026-06-16, context7)
Стиль и имена медиа-полей задаются в карточке (`providers.wavespeed`), смены кода не требуют:

1. **v3 JSON** (по умолчанию): `POST api/v3/<path>`; кадры — строковые поля изображения
   (URL/data-URI base64 через `_media`). Имена полей настраиваются:
   ```yaml
   wavespeed:
     id: "vidu/start-end-to-video-q2-turbo"
     media: { start: start_frame, end: end_frame }   # дефолт image / end_image
   ```
2. **v1 multipart** (`api: v1_multipart`): `POST api/v1/<path>` с **загрузкой файлов**
   кадров (`start_frame=@`/`end_frame=@`); локальные пути обязательны (http/data-URI → ошибка):
   ```yaml
   wavespeed: { id: "vidu/turbo/start-end-to-video", api: v1_multipart,
                media: { start: start_frame, end: end_frame } }
   ```
   Кодировщик — `WaveSpeedProvider._encode_multipart`; poll/result — общий v3
   `predictions/<id>/result`.

**Vidu Q2 Turbo** доступен обоими путями: v3 `vidu/start-end-to-video-q2-turbo`
(параметры: `start_frame`,`end_frame` required, `prompt`,`duration` 1–10,
`resolution` 540p/720p/1080p, `movement_amplitude`, `bgm`, `seed`) ИЛИ v1-multipart
`vidu/turbo/start-end-to-video`. В карточке по умолчанию — v3 JSON.

## Разрешение и aspect_ratio: решает карточка

Схемы WaveSpeed строгие (`additionalProperties: false` во всех проверенных
2026-09-12): поле, которого у модели нет, — это HTTP 400, а не молчаливый игнор.
Конвейер же шлёт `resolution` и `aspect_ratio` всегда. Что с ними делать,
объявляет карточка (`providers.wavespeed`), а не ветвление по id в адаптере:

| Ключ | Смысл |
|---|---|
| `resolution_style: size` | схема знает только `size` «W*H» (flux, seedream v4.5, z-image) |
| `resolution_style: k` | k-нотация `0.5k/1k/2k/4k` (nano-banana, grok-imagine-image) |
| `resolution_style: map` + `resolution_map` | своя сетка, наши значения переводятся таблицей карточки (minimax-h3: 720p → 768p) |
| `resolution_style: omit` | ни `resolution`, ни `aspect_ratio` в схеме нет (kling) |
| `omit_aspect_ratio: true` | `resolution` шлём как есть, а `aspect_ratio` в схеме нет (grok-видео, minimax-h3) |

`map` появился 2026-09-12: у minimax-h3 сетка `480p/540p/768p/1080p`, и 720p в ней
НЕТ. «Ближайшее» адаптер выбирать не имеет права — молчаливый переход на 480p
означал бы оплату заказанного качества по факту другого; соответствие пишет человек
в карточке. Несоответствие ловится ДО сметы (`_provider_preflight`), а не отказом
сабмита посреди оплаченного батча.

## Каталог как источник цен (бесплатно)

`GET /api/v3/models` (Bearer) отдаёт ~1030 моделей: `model_id`, `base_price`, `type`
и полную `api_schema` с перечислением полей и enum'ов. Это единственный способ
узнать путь и цену, не тратя денег. `base_price` — цена ГЕНЕРАЦИИ на дефолтных
параметрах (у видео это обычно 5 с): у `kling-v3.0-std` каталожные $0.42 сошлись с
живым списанием 2026-07-08 копейка в копейку, поэтому карточки, открытые по
каталогу, пересчитывают секунду как `base_price / 5`. Зависимость цены от
разрешения каталог НЕ объявляет — поэтому у таких карточек нет `res_mult`, и первая
живая генерация обязана сверить списание дельтой баланса.

### Подтверждено живьём — больше не проверять
- **Имена полей кадров в v3 JSON.** У Vidu Q2 Turbo это `image` / `last_image` (схема
  `/api/v3/models`, генерация 2026-07-08). Прежняя догадка `start_frame`/`end_frame`
  неверна — имена задаются в карточке полем `media`, у каждой модели свои.
- **Путь Seedance 2.0.** `bytedance/seedance-2.0-fast/image-to-video`, генерация
  2026-08-01. Прежняя догадка `bytedance/seedance-v2-fast/image-to-video` (через `v2`
  вместо `2.0`) неверна. Семейство `seedance-2.0-*` независимо подтверждено сторонним
  потребителем API: [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo)
  держит в конфиге `wavespeed_text_to_video_model = "bytedance/seedance-2.0-fast/text-to-video"`
  — тот же префикс, другой хвост под свою задачу.

### Сверить на спайке
- Ответ v1-multipart submit (предполагаем `{data:{id,urls.get}}`, как v3) и базовый URL
  v1 (`/api/v1` vs `/v1`, http vs https — в доке встречалось `http://api.wavespeed.ai/v1/...`).
- Цены 1080p у scaled-моделей: множители в карточках — из каталожной формулы, живой
  генерации в 1080p не было ни у одной видеомодели.
- Минимальная длительность отрезка. MoneyPrinterTurbo клампит запрос к
  `seedance-2.0-fast` в 4–15 секунд, то есть у их эндпоинта есть нижняя граница 4с.
  Наши отрезки — 5с (`quality_mode: high`) и 10с (`budget`), в диапазон попадают, но
  граница у image-to-video не проверена.
