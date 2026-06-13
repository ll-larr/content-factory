# Фаза 2 (звук + сборка) — статус выполнения (handoff)

**Обновлено:** 2026-06-13 (ночь; кодовые задачи 1/3/4/5 завершены автономно и отревьюены).
**Ветка:** `phase-2-sound-assembly` (НЕ смержена в master).
**Спека:** `docs/superpowers/specs/2026-06-12-phase2-sound-assembly-design.md`
**План:** `docs/superpowers/plans/2026-06-12-phase2-sound-assembly.md`

## Процесс выполнения

superpowers:subagent-driven-development: свежий субагент-исполнитель (sonnet) на задачу
→ spec-ревью (haiku) → quality-ревью (sonnet) → фиксы отдельным коммитом с повторным
ревью. Тесты строго `.\.venv\Scripts\python.exe -m pytest -q` из корня репо (venv не
активировать). ffmpeg обязателен в окружении (стоит через winget).

## Статус задач плана

| Задача | Статус | Детали |
|---|---|---|
| Task 1: ffmpeg_tools + assemble.py (видео-only) + гейт отрезков | ✅ done | commits `846aaf0` + `88a06de` (фикс ревью: probe после сборки не роняет процесс, косметика); оба ревью пройдены |
| Task 2: спайк аудио-моделей + карточки | ⏸ ОЖИДАЕТ ПОЛЬЗОВАТЕЛЯ | тратит кредиты (~6–8 кр) + нужно прослушать голоса вместе. НЕ начат автономно |
| Task 3: audio_plan.py + validate_audio_model + стадия `audio` | ✅ done | commits `b8b501c` + `6587c20` (фиксы ревью: явная ошибка на missing segment, assert audio_plan, rename audio_problems, +2 теста); оба ревью пройдены |
| Task 4: mix_audio.py — сведение | ✅ done | commits `54f57c6` + `e1f7975` (фиксы ревью: ManifestError→FfmpegError, единый формат ошибки, тесты tmp/amix); оба ревью пройдены |
| Task 5: наложение звука в assemble.py | ✅ done | commits `bafa563` + `15a80b5` (фикс ревью: `-shortest` в отдельный список опций, assert длительности overlay); оба ревью пройдены |
| Task 6: финальный боевой smoke на `_smoke` | ⏸ ОЖИДАЕТ ПОЛЬЗОВАТЕЛЯ | тратит кредиты (~5–10 кр) + прослушать результат. НЕ начат автономно |

**Полный тестовый набор: 152 passed** (было 108 на старте фазы 2; +44 за задачи 1/3/4/5).
**Финальное холистическое ревью кода (Tasks 1/3/4/5):** критичных проблем нет, интеграционные
швы (audio.json → generate_batch → манифест → mix_audio → assemble) согласованы, готово к спайку+smoke.

## ⛔ Почему Tasks 2 и 6 не сделаны автономно

Обе тратят кредиты Higgsfield. Стоящее правило проекта: **траты кредитов — только с
подтверждением пользователя**. Плюс на балансе на конец фазы 1 было ~0.5 кр — на спайк
(~6–8 кр) и smoke (~5–10 кр) не хватает. Перед обеими задачами: **пополнить кредиты**
и подтверждать каждую трату (как в фазе 1).

## Следующие шаги (для пользователя, по порядку)

### Task 2 — спайк аудио-моделей (см. план §"### Task 2")
Цель: разведать каталог голосов Inworld, формат файлов, цену на длинном тексте,
лимиты duration музыки/SFX, русский язык → заполнить карточки
`knowledge/audio/{inworld_text_to_speech,mirelo_text_to_audio,sonilo_music}.md`
(status: verified). **После спайка**: если реальное расширение файлов НЕ `.mp3` —
поправить `AUDIO_EXT` в `scripts/generate_batch.py:30` (+ комментарий) и `.mp3`-ассерты
в `tests/test_generate_batch.py::test_audio_happy_path`.

Бесплатно (без кредитов) уже известно из разведки на брейншторме — занести в карточки:
- `inworld_text_to_speech`: params `--prompt` + `--voice` (оба обязательны; имя голоса
  сметой НЕ валидируется); смета 2 кр/генерация, не зависит от длины текста на пробах.
  Inworld TTS-1.5: 15 языков вкл. русский в production-качестве; TTS-2: 100+ языков,
  один голос через все языки. Голоса-кандидаты из доков (проверить генерацией): Ashley, Hades.
- `mirelo_text_to_audio` (SFX): params `--prompt` + `--duration`; смета 1.25 кр / 5 с.
- `sonilo_music` (музыка): params `--prompt` + `--duration`; смета 1.88 кр / 30 с.
- Контракт CLI общий с видео: `generate cost|create|get`, результат по `result_url` (см.
  `knowledge/higgsfield-cli.md`). Субкоманды download нет.

### Task 6 — боевой smoke на `projects/_smoke` (см. план §"### Task 6")
В `_smoke` уже есть 2 кадра + 1 отрезок kling3_0 (5с), все `done`. Шаги:
1. Написать `projects/_smoke/episodes/ep01/audio.json` (1 реплика + 1 музыка + 1 SFX;
   голос и duration — из карточек Task 2). Шаблон — в плане.
2. `python scripts/generate_batch.py --project projects/_smoke --episode ep01 --stage audio`
   (смета ~5 кр → подтвердить).
3. Ревью звука: `python scripts/review.py --project projects/_smoke list --status generated`
   → прослушать → `... accept ep01/audio/vl-01 ep01/audio/mus-01 ep01/audio/sfx-01`.
4. `python scripts/mix_audio.py ...` → `python scripts/assemble.py ...` → посмотреть mp4
   со звуком. При плохом балансе громкостей — поправить константы
   `VOICE_VOLUME/SFX_VOLUME/MUSIC_VOLUME/DUCK` в `scripts/mix_audio.py` и пересвести (бесплатно).
5. Проверить resume (повторный `--stage audio` → «Всё уже сгенерировано», 0 трат).
6. Дописать этот файл фактическими списаниями и наблюдениями.
7. superpowers:finishing-a-development-branch с пользователем (судьба ветки).

## Housekeeping из финального ревью (не блокеры; фаза 3 / по случаю)

- `ACCEPTED = {"done","accepted_with_notes"}` дублируется: модульная константа в assemble.py
  и mix_audio.py, но локальная `accepted` внутри `main()` в generate_batch.py — при добавлении
  статуса легко забыть третью копию. Кандидат: вынести в `factory/manifest.py`.
- Путь к файлу отрезка `episodes/<ep>/segments/{n:03d}.mp4` строится в трёх местах
  (generate_batch, assemble, mix_audio) — TODO на вынос в `factory/shots.py` (фаза 3;
  сейчас все три согласованы).
- CLAUDE.md обновлён: `audio_plan` и `ffmpeg_tools` добавлены в список пакета factory.
