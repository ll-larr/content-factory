# Фаза 2 (звук + сборка) — статус выполнения (handoff)

**Обновлено:** 2026-06-13 (фаза 2 ФИНАЛИЗИРОВАНА: код готов, конвейер доказан; CLI-TTS
нефункционален → реальный TTS вынесен в отдельную задачу на ElevenLabs, спека §3).
**Ветка:** `phase-2-sound-assembly`.

> **Решение пользователя 2026-06-13:** финализировать фазу 2 в текущем виде. Звуковой
> конвейер (генерация music/SFX → ревью → сведение → сборка) реализован и доказан на
> реальном звуке; голосовой источник (TTS) переносится на ElevenLabs отдельной задачей,
> т.к. CLI-модель Higgsfield `inworld_text_to_speech` не генерирует (см. карточку и §блокер).
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
| Task 2: спайк аудио-моделей + карточки | 🟡 ЧАСТИЧНО | Mirelo + Sonilo **verified** генерацией (commit `e9dee94`); **Inworld TTS заблокирован** — формат `voice` неизвестен (см. ниже). Карточки записаны |
| Task 3: audio_plan.py + validate_audio_model + стадия `audio` | ✅ done | commits `b8b501c` + `6587c20` (фиксы ревью: явная ошибка на missing segment, assert audio_plan, rename audio_problems, +2 теста); оба ревью пройдены |
| Task 4: mix_audio.py — сведение | ✅ done | commits `54f57c6` + `e1f7975` (фиксы ревью: ManifestError→FfmpegError, единый формат ошибки, тесты tmp/amix); оба ревью пройдены |
| Task 5: наложение звука в assemble.py | ✅ done | commits `bafa563` + `15a80b5` (фикс ревью: `-shortest` в отдельный список опций, assert длительности overlay); оба ревью пройдены |
| Task 6: финальный боевой smoke на `_smoke` | 🟡 ЧАСТИЧНО | music+SFX прогнаны сквозь конвейер (commit `facd971`): generate→review→mix→assemble = **mp4 со звуком (h264+aac, 5.04с)**. Голос+полный smoke ждут разблокировки `voice` |

**Полный тестовый набор: 153 passed** (было 108 на старте фазы 2; +45: задачи 1/3/4/5 + фикс AUDIO_EXT).
**Финальное холистическое ревью кода (Tasks 1/3/4/5):** критичных проблем нет, интеграционные
швы (audio.json → generate_batch → манифест → mix_audio → assemble) согласованы.

## Результаты спайка + частичного smoke (2026-06-13, баланс 200.56 → 198.92 кр)

**Спайк (Task 2):**
- **Mirelo (SFX)** ✅ verified: выход `.mp3` (mono, 44.1 кГц), цена **0.25 кр/с** линейно.
- **Sonilo (музыка)** ✅ verified: выход `.m4a`/aac (stereo, 44.1 кГц), цена **0.0625 кр/с** линейно.
- **Inworld (TTS)** ❌ блокер (см. ниже).
- **Находки:** форматы файлов РАЗНЫЕ по моделям → `AUDIO_EXT` исправлен на деривацию из
  `result_url` (commit `619fb0b`, +1 тест). **Провал генерации кредиты НЕ списывает.**
  Длительность Mirelo/Sonilo соблюдается; верхнего предела `--duration` смета не отбивает.

**Частичный smoke (Task 6):** `projects/_smoke` — сгенерированы music (Sonilo 5с) + SFX
(Mirelo 2с) через `generate_batch --stage audio`, приняты ревью (review.py accept),
сведены `mix_audio.py` (ducking, mix.m4a 5.04с), собраны `assemble.py` → финальный
`ep01.mp4` (h264 видео + aac звук, обе дорожки 5.04с). **Весь конвейер доказан на
реальном звуке.** Медиа на диске (в git не коммитим — .gitignore). Качество звука НЕ
прослушано (нет слуха у ассистента).

## 🚧 ЕДИНСТВЕННЫЙ ОСТАВШИЙСЯ БЛОКЕР: формат `voice` для Inworld TTS

Штатные имена голосов Inworld (Ashley, Hades, Olivia, Dennis, Mark, lowercase) в CLI
Higgsfield → `status: failed`, пустой `result_url`, без текста ошибки, **без списания**.
Mirelo/Sonilo (тот же тип audio, без voice) работают → проблема именно в значении `voice`.
CLI не листит голоса; публичные доки Higgsfield аудио не покрывают. **Вероятно нужен
UUID/слаг из авторизованного веб-UI (Speak/Audio).** Детали — `knowledge/audio/inworld_text_to_speech.md`.

### Что осталось (после получения рабочего `voice`)
1. Подставить значение, сгенерировать 1 реплику (2 кр) → проверить формат файла →
   обновить карточку Inworld в `verified` + `output_format`.
2. Добавить `voice_lines` в `projects/_smoke/episodes/ep01/audio.json`, прогнать
   `--stage audio` (resume сгенерирует только голос), accept, `mix_audio`, `assemble` →
   полный smoke с речью+музыкой+SFX. Resume music/SFX НЕ перегенерирует (уже done).
3. Проверить русский TTS (Inworld держит ru). Прослушать баланс громкостей; при нужде —
   крутить `VOICE_VOLUME/SFX_VOLUME/MUSIC_VOLUME/DUCK` в `mix_audio.py` (бесплатно).
4. superpowers:finishing-a-development-branch (судьба ветки).

## Housekeeping из финального ревью (не блокеры; фаза 3 / по случаю)

## Housekeeping из финального ревью (не блокеры; фаза 3 / по случаю)

- `ACCEPTED = {"done","accepted_with_notes"}` дублируется: модульная константа в assemble.py
  и mix_audio.py, но локальная `accepted` внутри `main()` в generate_batch.py — при добавлении
  статуса легко забыть третью копию. Кандидат: вынести в `factory/manifest.py`.
- Путь к файлу отрезка `episodes/<ep>/segments/{n:03d}.mp4` строится в трёх местах
  (generate_batch, assemble, mix_audio) — TODO на вынос в `factory/shots.py` (фаза 3;
  сейчас все три согласованы).
- CLAUDE.md обновлён: `audio_plan` и `ffmpeg_tools` добавлены в список пакета factory.
