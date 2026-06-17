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
- Полная «конституция завода» (этапы, чекпоинты, скиллы) появится в фазе 3.
