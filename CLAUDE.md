# content-factory

ИИ-конвейер создания видео: от брифа до готовой серии со звуком.
Спека: docs/superpowers/specs/2026-06-11-content-factory-design.md

## Структура
- scripts/factory/ — Python-пакет (project, manifest, models, shots, audio_plan, ffmpeg_tools)
- scripts/factory/providers/ — слой провайдеров видео/фото (base + wavespeed/runware/openrouter, фабрика get_provider)
- scripts/generate_batch.py — батч-генерация кадров/отрезков
- scripts/review.py — ревью генераций: accept/reject/requeue (статусы манифеста)
- scripts/mix_audio.py — сведение аудиодорожки эпизода (тайминг по audio.json)
- scripts/assemble.py — сборка финального mp4 из отрезков (+звук, если сведён)
- knowledge/ — карточки моделей (матрица возможностей + best practices) и контракт CLI
- projects/ — контент-проекты (project.json, manifest.json, bible/, episodes/)
- tests/ — pytest

## Правила
- Скрипты запускаются ИЗ КОРНЯ репозитория (пути knowledge/ и projects/ — относительные).
- Тесты: `pytest -q`. Перед коммитом тесты должны быть зелёными.
- Изоляция провайдера: точные эндпоинты/флаги/model-id КАЖДОГО провайдера живут ТОЛЬКО
  в его адаптере (scripts/factory/providers/<name>.py) и его knowledge-доке
  (knowledge/<name>-api.md) — больше нигде. Ключи — из env, не хардкодить.
- Провайдер/модель/тир/разрешение выбираются в project.json (дефолт провайдера — по типу
  контента). Дизайн рефактора: docs/superpowers/specs/2026-06-15-provider-refactor-design.md.
- Higgsfield вырезан. Генерация звука (TTS/music/sfx) вынесена в отдельную задачу
  (ElevenLabs); стадия audio в generate_batch отключена, mix_audio/assemble сохранены.
  Фаза звука отложена пользователем 2026-08-01 — провайдер TTS/SFX/музыки не выбран,
  начинать с superpowers:brainstorming, не с кода.
- Кадр после скачивания нормализуется в настоящий PNG (`ffmpeg_tools.ensure_png`,
  вызывается из generate_batch.py). Провайдер может отдать не-PNG (например JPEG) под
  именем `NNN.png` — расширение не гарантирует формат содержимого, только код это чинит.
- У провайдера есть хук `preflight_problems(model, params)` (`providers/base.py`,
  переопределяется в адаптере), который отбивает несовместимые параметры ДО сметы —
  `generate_batch.py` вызывает его сразу после валидации карточки и выходит кодом 2.
  Нужен, чтобы смета не обещала цену, которую submit не может выполнить.
- Гейт трат (`status: skeleton` → exit 2) — КАРТОЧНОГО уровня: `validate_video_model`
  смотрит общий `status`, не на конкретного провайдера и не на тир. Поэтому в карточке
  со `status: verified` должны оставаться раскомментированными ТОЛЬКО те блоки
  `providers` и тиры, которые подтверждены живой генерацией; остальные — закомментированы
  (тогда валидатор отдаёт «not available on provider», а `_concrete_id` — «неизвестный
  tier», оба до сети). Раскомментировать по одному, вместе с фактической ценой из
  живого прогона. Живые пробы дважды показали, что догадки по ценам врут в разы.
- Нормализация разрешения между отрезками в `assemble.py` СОЗНАТЕЛЬНО не делается
  (решение 2026-08-01): разный resolution отрезков внутри эпизода — ошибка конфигурации,
  падение ffmpeg с понятной ошибкой честнее молчаливого апскейла.
- Полная «конституция завода» (этапы, чекпоинты, скиллы) появится в фазе 3.
