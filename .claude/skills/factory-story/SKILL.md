---
name: factory-story
description: Написать идею, сквозной сюжет сезона и стайл-гайд серии. Этап 3 конвейера пре-продакшна, чекпоинт. Триггер - /factory-story
---

# Идея, сквозной сюжет, стайл-гайд

## Перед работой

1. Проверь гейт. Закрыт — остановись и покажи причины, ничего не пиши:
   ```bash
   python scripts/factory.py check --project <проект> --stage story
   ```
   Этап 3 не требует ничего, кроме валидного `project.json`
   (`STAGE_REQUIRES["story"]` пусто в `scripts/factory/preprod.py`) — сам
   `factory.py` уже отказал бы кодом 1 раньше, если `project.json` нет. На
   практике этот гейт закрытым почти не бывает; если всё же закрыт — читай
   причины и останавливайся, как на любом другом этапе.
2. Прочитай `project.json` (тип контента, тема, аудитория, число и
   длительность серий, язык), `research.md` (если есть — этап 2
   необязательный), `bible/craft-notes.md` (если файла ещё нет — читать
   нечего, это нормально для первого прогона проекта; если есть — свод правил
   ремесла, читай целиком, файл небольшой и кодом по разделам не делится).

## Что написать

Три файла. `factory.py init` уже создал их пустыми заготовками с проставленным
`kind` — не меняй `kind`, дописывай `status` и тело:

- `bible/idea.md` (`kind: idea`) — главная идея сериала, тон, почему это
  интересно аудитории из `project.json.audience`.
- `bible/season-arc.md` (`kind: season-arc`) — сквозной сюжет на весь сезон
  (`project.json.episodes` серий), поэпизодная дуга.
- `bible/style-guide.md` (`kind: style-guide`) — визуальный стиль. Обязателен
  блок между маркерами:
  ```markdown
  <!-- canonical:style -->
  flat 2D cartoon, thick outlines, saturated palette, ...
  <!-- /canonical:style -->
  ```
  Только описание картинки, по-английски, без пересказов и настроенческих
  прилагательных — этот текст ДОСЛОВНО подставится в `{{style}}` каждого
  промпта кадра на этапе 6 (`factory.prompts.expand_prompt`, спека §10).

  **Важно и не проверяется кодом:** в отличие от карточек персонажей (там
  `factory/preprod._cast_problems` проверяет `has_canonical(card,
  "appearance")` и держит гейт `storyboard` закрытым без блока), для
  `style-guide.md` такой проверки в `stage_gate` НЕТ — гейт этапа `storyboard`
  смотрит только на `status: approved` файла, не на наличие блока
  `canonical:style`. Если блок забыть, `factory.py check --stage storyboard`
  всё равно откроется, а `expand_prompt` упадёт необработанным `PromptError`
  уже во время платной отправки кадров в `generate_batch.py`. Единственная
  защита сейчас — твоя внимательность здесь и повторная проверка в
  `factory-storyboard`. Не пропусти блок.

У всех трёх файлов — `status: draft` во frontmatter.

## После записи

1. Закоммить все три файла сразу после записи, до правок человека — это база
   для `factory.py diff`:
   ```bash
   git add <проект>/bible/idea.md <проект>/bible/season-arc.md <проект>/bible/style-guide.md
   git commit -m "draft(preprod): story <проект>"
   ```
2. Дайджест (протокол чекпоинта, базовая спека §5): пересказ идеи и сквозного
   сюжета на 7–10 предложений + логлайн каждой серии одной строкой + что
   изменилось после прошлых правок пользователя (если это не первый прогон —
   сравни через `factory.py diff --project <проект> bible/idea.md` и
   аналогично для двух других файлов) + открытые вопросы. Полные файлы — по
   путям, не пересказывай их целиком. Останови работу здесь и жди.
3. **Не проставляй `status: approved` сам.** Человек одобряет каждый файл
   отдельной командой:
   ```bash
   python scripts/factory.py approve --project <проект> bible/idea.md
   python scripts/factory.py approve --project <проект> bible/season-arc.md
   python scripts/factory.py approve --project <проект> bible/style-guide.md
   ```
   Порядок одобрения не важен для механики (`depends_on` считается по
   фактическим хешам в момент вызова `approve`), но `season-arc.md` и
   `style-guide.md` оба зависят от `idea.md`: если одобрить их раньше, а
   потом ещё раз поправить `idea.md`, они станут `stale_deps` — это ожидаемое
   поведение гейта, а не баг, объясни это человеку, если он удивится.
