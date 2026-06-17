# Видео-модели и провайдеры: выбор + провайдер-абстракция

> Дата: 2026-06-13. Аналитическая записка + архитектурное предложение.
> Цель — выбрать модели под конвейер content-factory (генерация отрезка
> интерполяцией между двумя ключевыми кадрами: end-кадр отрезка N =
> start-кадр отрезка N+1, spec §4/§99) И заложить возможность переключать
> поток между провайдерами (fal.ai сейчас, OpenRouter — потом) без переписывания
> бизнес-логики.
> Цены и матрицы start/end быстро меняются — перед завязкой проверять пробами.

## 0. Решение в одну строку

Запускаемся на **fal.ai**, но не вшиваем его в код. Вводим **общий интерфейс
провайдера** (как сейчас сделан `higgsfield_client`), за которым прячутся адаптеры
`fal`, `openrouter`, `higgsfield`. Активный провайдер — поле в `project.json`.
OpenRouter подключается позже сменой одной строки конфига, а не рефакторингом.

---

## 1. Задача и критерий отбора

Нужна генерация **по первому И последнему кадру** (start/end). Это отсекает модели
с одним входным изображением.

- **НЕ принимают end-кадр** (разведка проекта 2026-06-12): `kling2_6`,
  `minimax_hailuo`, `veo3`, `veo3_1` (на Higgsfield), Pika. → мимо.
- **Принимают start+end** — кандидаты в §2.

Важно: поддержка end-кадра **зависит от связки модель×провайдер** (тот же `veo3_1`
на Higgsfield end не берёт, у Google/др. — берёт). Поэтому матрицу возможностей
ведём с привязкой к провайдеру (см. §5).

## 2. Рынок моделей со start/end (2026)

| Модель | Разработчик | Start/End | Цена (ориентир) | Сильная сторона |
|---|---|---|---|---|
| **Vidu Q1/Q2 Start-End-to-Video** | Vidu | ✅ профильно | ~$0.07/с | «Мост между 2 кадрами» + топ-стилизация (2D/аниме) |
| **Seedance 2.0 / 1.5 Pro** | ByteDance | ✅ | от **$0.022/с** | Самая дешёвая зрелая, живое движение |
| **Wan 2.7 / Wan2.1-FLF2V** | Alibaba | ✅ first-last | $0.2/480p, $0.4/720p | Open-weights → self-host, LoRA под стиль |
| **Kling 3.0** | Kuaishou | ✅ + multi-shot | ~$0.05–0.10/с | Консистентность персонажа 10с, кино |
| **Luma Ray2 / Ray Flash 2** | Luma | ✅ | дешевле Runway | Предсказуемый keyframe-контроль |
| **Runway Gen-4 Turbo** | Runway | ✅ (+ middle) | дорого | Лучший «пульт» движения |
| **Veo 3.1** | Google | частично ✅ | премиум | Фотореализм, лица, диалоги |

Проверено генерацией в самом проекте (verified): `kling3_0`, `seedance1_5`.
Остальные карточки — skeleton (нужен спайк).

## 3. Маршрутизация модели по типу контента

Хардкодить одну модель нельзя — фаворит зависит от формата.

### Мультфильм (2D / аниме)
Реалистичные модели «перерисовывают» стиль (в карточке проекта это отмечено
для Kling 3.0: контуры мягче исходного flat 2D).
- **Дефолт:** **Vidu** (держит стиль + профильный Start-End).
- **Апгрейд под свой стиль:** **Wan + LoRA**.
- Не брать Kling/Veo на чистом 2D. Режим budget 10с.

### Научпоп
Много разнородных сцен; решает цена за объём.
- **Дефолт:** **Seedance** или **Wan 2.2 Turbo** ($0.02/с).
- Говорящий ведущий с синхроном губ → **Veo 3.1** точечно (звук — отдельная фаза).
- Режим budget 10с; на статике добавлять micro-движение камеры.

### Сериал (реализм, сквозные персонажи)
- **Дефолт:** **Kling 3.0** (стабильный персонаж 10с, multi-shot, кино-свет).
- **Премиум-кадры:** **Veo 3.1**.
- **Из своих рефов:** **Seedance 2.0** (9 img + 3 video + 3 audio).
- Режим HQ 5с; без резкой смены композиции start↔end.

### Сводка
| Формат | Видео дефолт | Видео апгрейд | Режим |
|---|---|---|---|
| Мультфильм | **Vidu** | Wan + LoRA | budget 10с |
| Научпоп | **Seedance / Wan Turbo** | Veo 3.1 (диктор) | budget 10с |
| Сериал | **Kling 3.0** | Veo 3.1 (премиум) | HQ 5с |

---

## 4. Провайдеры (для контекста выбора)

| Провайдер | Плюсы | Минусы | Роль |
|---|---|---|---|
| **fal.ai** | ~600+ моделей (Kling, Seedance, Wan FLF, Luma, Vidu, Veo), дёшево, быстрый инференс, хорошие SDK | свой формат на модель | **Основной сейчас** |
| **OpenRouter** | нормализованный `frame_images` (`first_frame`/`last_frame`) на все модели; `/api/v1/videos/models` → `supported_frame_images`; один ключ/биллинг | возможно нет Vidu; цена = проброс; фича с апр.2026 | **Заложить, включить позже** |
| **WaveSpeedAI** | явные endpoint'ы Vidu Start-End и Wan FLF | — | альтернатива под Vidu |
| **Higgsfield** (текущий) | уже интегрирован (CLI-адаптер) | API за дорогими тарифами, скудные docs | оставить адаптером/легаси |

Почему именно так: **сейчас** fal даёт самый широкий набор нужных моделей (включая
Vidu для мультфильмов) по низкой цене — стартуем на нём. **Потом** OpenRouter ценен
нормализованным start/end-интерфейсом, который 1-в-1 ложится на матрицу
knowledge-карточек; переключимся, когда дозреет и подтвердим наличие нужных моделей.

---

## 5. Архитектура: провайдер-абстракция

Цель — менять провайдера через конфиг, бизнес-логику (`generate_batch.py`,
манифест, ревью) не трогать. Опираемся на то, что `higgsfield_client` уже
по сути адаптер — обобщаем его в интерфейс.

### 5.1 Общий интерфейс провайдера
Единый протокол (ABC/`typing.Protocol`) в `scripts/factory/providers/base.py`:

```
class VideoProvider(Protocol):
    name: str
    def cost(self, job: Job) -> Cost: ...          # смета до запуска
    def create(self, job: Job) -> list[str]: ...   # → список job_id
    def get(self, job_id: str) -> JobStatus: ...    # status + result_url
    def poll(self, job_id: str, timeout) -> JobStatus: ...  # дефолт через get()
```

Текущие функции `higgsfield_client` переезжают в
`providers/higgsfield.py::HiggsfieldProvider` без изменения поведения.

### 5.2 Провайдер-агностичный Job
Нормализованный словарь-запрос — единый для всех провайдеров (он уже почти такой
в `_params_to_flags`: `refs` / `start_frame` / `end_frame`):

```
Job = {
  "model":        "seedance",     # логический id, НЕ id провайдера
  "prompt":       "...",
  "start_frame":  "<path>",
  "end_frame":    "<path|None>",
  "refs":         ["<path>", ...],
  "duration":     5,
  "aspect_ratio": "16:9",
  "resolution":   "720p",
  "sound":        False,
}
```

Каждый адаптер сам мапит нормализованный Job → свой формат:
- **Higgsfield:** в CLI-флаги (`--start-image`/`--end-image`/`--image`) — как сейчас.
- **fal:** REST: загрузка кадров → endpoint модели → queue/poll → result_url.
- **OpenRouter:** `POST /api/v1/videos`, кадры через `frame_images`
  (`{frame_type: first_frame|last_frame}`), async-поллинг.

### 5.3 Реестр моделей (важная правка карточек)
Один логический `model` имеет **разные id у разных провайдеров**. В knowledge-карточку
добавляем карту провайдеров и провайдеро-зависимую матрицу start/end:

```yaml
# knowledge/video/seedance.md (frontmatter)
model: seedance
providers:
  higgsfield: { id: seedance1_5, supports_start_end: true,  durations: [4,8,12] }
  fal:        { id: "fal-ai/bytedance/seedance/v1.5/pro",   supports_start_end: true, durations: [...] }
  openrouter: { id: "bytedance/seedance-1.5",               supports_start_end: true, durations: [...] }
```

Так `supports_start_end` и сетка длительностей живут **по связке модель×провайдер** —
это и есть причина, почему veo3_1 «не берёт end на Higgsfield, но берёт у Google».

### 5.4 Выбор провайдера
- Поле `video_provider` в `project.json` (default: `"fal"`).
- Фабрика `get_provider(name) -> VideoProvider` в `providers/__init__.py`.
- В `generate_batch.py` заменить `from factory import higgsfield_client as hf`
  на `provider = get_provider(project.video_provider)`; вызовы
  `hf.cost/create/get` → `provider.cost/create/get`.
- Возможен **per-content-type override**: дефолт-модель и даже провайдер из §3
  (напр. мультфильм → Vidu; если на активном провайдере Vidu нет — взять fal).

### 5.5 Этапы внедрения (ничего не ломаем)
1. **A. Извлечь интерфейс.** Завернуть текущий Higgsfield в `HiggsfieldProvider`
   под `VideoProvider`. Поведение не меняется, тесты зелёные. Релиз без рисков.
2. **B. Добавить `FalProvider`** и переключить дефолтный поток на fal
   (`video_provider: "fal"`). Higgsfield остаётся рабочим адаптером.
3. **C. Добавить `OpenRouterProvider`** за тем же интерфейсом. Включается сменой
   `video_provider` в `project.json`, когда подтвердим модели и цену.

Инварианты при переключении: смета (`cost`) до батча, идемпотентный манифест,
формат job_id-ов, скачивание по `result_url` — общие для всех адаптеров.

---

## 6. Рекомендация

1. **Сейчас:** этапы A→B. Интерфейс + `FalProvider`, дефолт `video_provider: "fal"`.
2. **Модель — параметр проекта**, привязать к типу контента (§3); реестр моделей
   с per-provider id и матрицей start/end (§5.3).
3. **OpenRouter — этап C**, втыкается адаптером позже без рефакторинга.
4. Рабочие лошадки: Seedance (объём), Kling 3.0 (персонаж), Vidu (стиль/стыки),
   Veo 3.1 — премиум точечно.

## 7. Что проверить перед интеграцией

- [ ] fal: точные endpoint-id и формат запроса для Seedance / Kling 3.0 / Vidu /
      Wan FLF (загрузка start/end, queue/poll, result_url).
- [ ] OpenRouter `GET /api/v1/videos/models`: есть ли Vidu; у каких моделей
      `last_frame` в `supported_frame_images`; цена нужных моделей.
- [ ] Сетки длительностей по провайдерам (Seedance 4/8/12 vs 5/10 конвейера).
- [ ] Пробы по 1–2 отрезка на своём контенте: интерполяция start→end, удержание
      стиля/персонажа, фактическое списание — Seedance vs Vidu vs Kling.
- [ ] Согласовать `Job`-схему так, чтобы все три адаптера мапились без потерь.

## Источники
- Atlas Cloud — Best/Cheapest AI Video Models 2026
- OpenRouter — Announcing Video Generation; Docs (video-generation, frame_images)
- fal.ai — Wan FLF2V, Luma Ray2; TeamDay — провайдеры; WaveSpeed — Vidu Start-End
- 3DAI Studio — Veo 3.1 vs Kling 3.0 vs Seedance 2.0
