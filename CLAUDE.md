# content-factory

ИИ-конвейер создания видео: от брифа до готовой серии со звуком.
Спека: docs/superpowers/specs/2026-06-11-content-factory-design.md

## Структура
- scripts/factory/ — Python-пакет (project, manifest, models, shots, higgsfield_client)
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
- Точные флаги Higgsfield CLI живут ТОЛЬКО в knowledge/higgsfield-cli.md
  и scripts/factory/higgsfield_client.py — больше нигде.
- Полная «конституция завода» (этапы, чекпоинты, скиллы) появится в фазе 3.
