# Higgsfield CLI — контракт (спайк 2026-06-12)

Источник правды для `scripts/factory/higgsfield_client.py`. Всё ниже проверено живыми
командами 2026-06-12 (CLI 0.1.40). Что НЕ проверено генерацией — помечено явно.

## Версия CLI и аутентификация

- `higgsfield 0.1.40` (npm `@higgsfield/cli`, глобально). Бинари-синонимы: `higgsfield`, `higgs`, `hf`.
- Авторизация: `higgsfield auth login` (браузер). Проверка: `higgsfield account status`
  → `atempro64@gmail.com — free plan, N credits`.
- В свежем PowerShell может понадобиться обновить PATH:
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`.
- Глобальные флаги: `--json` (сырой JSON — использовать ВСЕГДА в скриптах), `--no-color`.

## Каталог моделей (фактические id)

`higgsfield model list --json` → массив `{display_name, job_set_type, type}`.
Модель адресуется по **job_set_type** (никаких kebab-case id из маркетинга).

⚠️ **Ловушка имён nano banana:**

| display_name | job_set_type | что это |
|---|---|---|
| Nano Banana 2 | `nano_banana_flash` | дешёвая рабочая лошадка (1.5 кр) |
| Nano Banana Pro | `nano_banana_2` | PRO-модель (2 кр) — id ВРЁТ |

⚠️ **Kling 2.0 / 2.1 / 2.5 в CLI НЕ СУЩЕСТВУЮТ.** Видео-Kling: только `kling2_6` и `kling3_0`.

Ключевые id: `nano_banana_flash`, `nano_banana_2`, `kling2_6`, `kling3_0`, `seedance_2_0`,
`seedance1_5`, `wan2_7`, `veo3`, `veo3_1`, `veo3_1_lite`, `minimax_hailuo`, `grok_video`,
`grok_video_v15`, `text2image_soul_v2`, `seedream_v4_5`, `seedream_v5_lite`, `grok_image`.
Параметры конкретной модели: `higgsfield model get <job_set_type> --json`
(enum/default/required по каждому параметру).

## Команды: смета / создание / статус / скачивание

Параметры передаются флагами `--имя_параметра значение`, имена — **snake_case из
`model get`** (`--aspect_ratio`, `--duration`, `--resolution`), НЕ kebab-case.
Медиа-флаги: `--image`, `--start-image`, `--end-image`, `--video`, `--audio` —
принимают локальный путь (автозагрузка) или UUID ранее загруженного медиа.

```powershell
# Смета — БЕСПЛАТНО, и при этом валидирует параметры и медиа-роли
higgsfield generate cost nano_banana_flash --prompt "..." --aspect_ratio 16:9 --resolution 1k --json
# → {"credits": 1, "credits_exact": 1.5}

# Создание задачи
higgsfield generate create nano_banana_flash --prompt "..." --aspect_ratio 16:9 --resolution 1k --json
# → ["f8350bb8-9e1b-4122-9932-2552d5e8ec1f"]   ← МАССИВ job id!

# Статус (без ожидания)
higgsfield generate get <job_id> --json

# Ожидание завершения (дефолт: timeout 10m, interval 3s)
higgsfield generate wait <job_id> --json --timeout 15m --interval 10s
```

**Команды `download` НЕТ.** Результат скачивать HTTP-ом по `result_url` из `get`/`wait`:
`Invoke-WebRequest -Uri $url -OutFile out.png` (Python: `urllib.request.urlretrieve`).

Прочее: `generate list` (последние задачи), `upload create <file>` / `upload list`
(ручная загрузка медиа, возвращает UUID).

## Жизненный цикл задачи

Статусы из `get`/`wait`: `in_progress` → `completed` (поле `status`).
Статус сбоя живьём не наблюдали — в адаптере считать терминальными `completed`
и любые не-`in_progress` (например `failed`), проверять наличие `result_url`.

Тайминги спайка: картинка nano_banana_flash — десятки секунд; видео seedance1_5
4с 720p — единицы минут. `wait` с запасом `--timeout 15m` хватило с избытком.

## Формат JSON-ответов (фактические примеры спайка)

`generate create` → `["af2b2bdb-7616-4ad2-8575-340f761b985f"]`

`generate get`/`wait` →
```json
{
  "id": "af2b2bdb-7616-4ad2-8575-340f761b985f",
  "status": "completed",
  "display_name": "Seedance 1.5 Pro",
  "job_set_type": "seedance1_5",
  "result_url": "https://d8j0ntlcm91z4.cloudfront.net/user_.../hf_..._af2b2bdb....mp4",
  "created_at": 1781213652.169595,
  "params": {
    "width": 1280, "height": 720,
    "prompt": "the cat slowly reaches toward the control panel, subtle camera push-in",
    "medias": [
      {"data": {"id": "2667d05c-...", "url": "https://...png", "type": "media_input"}, "role": "start_image"},
      {"data": {"id": "d98241f9-...", "url": "https://...png", "type": "media_input"}, "role": "end_image"}
    ],
    "duration": 4, "resolution": "720p", "aspect_ratio": "16:9",
    "seed": 352868, "generate_audio": true
  }
}
```

`generate cost` → `{"credits": 4, "credits_exact": 4.8}` (`credits` округлён, брать `credits_exact`).

## Референс-изображения и загрузка файлов

`--image local.png` автозагружает файл (в `params.medias[]` появляется запись с
`role: "image"` и UUID). Проверено генерацией: nano_banana_flash со вторым кадром
по референсу первого — персонаж, стиль и окружение сохранены. UUID из `medias[].data.id`
можно переиспользовать в следующих командах вместо повторной загрузки.

## Start/end кадры: какие видеомодели поддерживают

Проверка `generate cost ... --start-image x.png --end-image y.png` (бесплатная
валидация контракта, 2026-06-12):

| Модель | start+end | Ответ CLI |
|---|---|---|
| `kling3_0` | ✅ принимает | смета 10 кр/5с |
| `seedance_2_0` | ✅ принимает | смета 22.5 кр/5с |
| `seedance1_5` | ✅ принимает | смета 4.8 кр/4с |
| `wan2_7` | ✅ принимает | смета 7.5 кр/5с |
| `veo3_1_lite` | ✅ принимает | смета 8 кр |
| `kling2_6` | ❌ | «Model accepts a single image input» |
| `veo3_1` | ❌ | «Model accepts a single image input» |
| `minimax_hailuo` | ❌ | «Model accepts only --image» |

**Проверено РЕАЛЬНОЙ генерацией: `seedance1_5`** — первый кадр видео = start-image,
последний = end-image, интерполяция плавная, персонаж стабилен (spike/seg1.mp4,
4.05с, 1280×720, 24fps). Остальные ✅-модели проверены только cost-валидацией;
визуальную интерполяцию kling3_0/seedance_2_0 подтвердить при первом боевом запуске.

## Стоимости, замеченные в спайке

- nano_banana_flash: **1.5 кр/картинка** (16:9, 1k; с референс-изображением — так же 1.5).
- seedance1_5: **4.8 кр** за 4с 720p (со start/end кадрами).
- Сметы без генерации: nano_banana_2 — 2; kling3_0 — 10/5с; kling2_6 — 10/5с;
  seedance_2_0 — 22.5/5с; wan2_7 — 7.5/5с; veo3_1_lite — 8; minimax_hailuo — 6.
- Списания совпали со сметами копейка в копейку: 10 → 8.5 → 7.0 → 2.2.

## Грабли

1. **Ловушка имён**: `nano_banana_2` — это PRO, а не «Nano Banana 2» (см. выше).
2. **`download`-команды нет** — качать HTTP-ом по `result_url`.
3. **`create` возвращает МАССИВ** job id (есть `batch_size`); для одиночной задачи брать `[0]`.
4. `generate cost` бесплатен и **валидирует медиа-роли** — использовать как предполётную
   проверку возможностей модели, не тратя кредиты.
5. `params.width/height` в ответах могут «плавать» между опросами одного job
   (наблюдали 1344×768 → 1376×768) — не считать стабильными.
6. Видео seedance1_5 пришло **с аудиодорожкой** (AAC; в params `generate_audio: true`,
   хотя в `model get` такого параметра нет). Для фазы 1 аудио игнорировать/вырезать в фазе 2.
7. Сетки длительностей у моделей РАЗНЫЕ: kling3_0 — integer (default 5);
   seedance1_5 — enum 4/8/12; kling2_6 — enum "5"/"10". Сверять с `model get`.
8. Флаги параметров — snake_case (`--aspect_ratio`), медиа-флаги — kebab-case
   (`--start-image`). Не путать.
9. В свежем PowerShell обновлять PATH (см. «Аутентификация»).
