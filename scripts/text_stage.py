"""Текстовая стадия одной командой: промпт из скилла, модель, файлы.

Запускать из корня репозитория:
  python scripts/text_stage.py --project projects/<проект> --stage story
  python scripts/text_stage.py --project projects/<проект> --stage script \
      --episode ep01 --request "больше про ворону"

  python scripts/text_stage.py --project projects/<проект> --stage factcheck \
      --episode ep01

Тот же путь использует панель: она запускает эту команду подпроцессом и
показывает её вывод. Логика стадии живёт в `factory/text`, здесь только разбор
аргументов и печать — как и у остальных CLI конвейера.

Коды выхода: 0 успех; 1 сбой движка или негодные данные стадии; 2 гейт стадии
не пускает (проверять нечего — сначала предыдущий этап); 3 проверка фактов не
пройдена (сценарий не одобрить).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.env import load_env                               # noqa: E402
from factory.text import factcheck as text_factcheck           # noqa: E402
from factory.text import stages as text_stages                 # noqa: E402
from factory.text.engine import TextEngineError, pick_engine   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _run_factcheck(args, project_dir: Path) -> int:
    """Проверка фактов идёт двумя проходами с поиском между ними.

    Отдельная ветка, а не общий путь: у стадии два вызова модели и поиск, и
    сводить это к «собрал промпт — записал файлы» значило бы соврать про то,
    что происходит. Оркестровка — в `factory/text/factcheck.py`, здесь только
    печать, как и у остальных CLI конвейера.
    """
    if not args.episode:
        print("проверка фактов идёт по серии: добавь --episode")
        return 1
    try:
        engine = pick_engine(args.engine)
    except TextEngineError as e:
        print(f"нечем писать: {e}")
        return 1

    print(f"движок: {engine.label}"
          + (f" · модель {args.model}" if args.model else ""))
    print(f"стадия: проверка фактов · серия {args.episode}")
    if args.request.strip():
        # Пожелание автора до проверяющего не доезжает СОЗНАТЕЛЬНО: он не верит
        # источнику автора по правилу жанра, и «эту дату проверять не надо»
        # было бы ровно тем указанием, ради которого проверку и заводили.
        # Молча проглотить строку нельзя — человек решит, что она учтена.
        print("текст запроса проверяющему не передан: у него пустой контекст "
              "по правилу жанра")
    try:
        result = text_factcheck.run(project_dir, ROOT, args.episode,
                                    engine=engine, model=args.model)
    except text_factcheck.FactCheckBlocked as e:
        # Код 2 — отказ по контракту входных данных, та же дисциплина, что у
        # ShotsError в generate_batch: техническим сбоем (1) это не является, и
        # путать их нельзя — лечится оно не повтором, а предыдущим этапом.
        print(f"проверка не начата: {e}")
        return 2
    except text_factcheck.FactCheckError as e:
        print(f"проверка не проведена: {e}")
        return 1

    for rel in result["written"]:
        print(f"записан {rel}")
    print(f"вердикт: {result['verdict']} (утверждений: {result['claims']})")
    if result["verdict"] != "passed":
        print("сценарий не одобрится, пока проверка не пройдена: "
              "почини факты и проверь заново")
        return 3
    print("готово. Одобрять сценарий — factory.py approve, "
          "status: approved стадия себе не ставит.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    ap.add_argument("--stage", required=True)
    ap.add_argument("--episode")
    ap.add_argument("--model")
    ap.add_argument("--engine")
    ap.add_argument("--request", default="")
    args = ap.parse_args(argv)

    load_env(ROOT)

    project_dir = Path(args.project)
    if args.stage == text_factcheck.STAGE_ID:
        return _run_factcheck(args, project_dir)

    try:
        prompt = text_stages.build_prompt(
            args.stage, project_dir, ROOT,
            request=args.request, episode=args.episode)
    except text_stages.StageError as e:
        print(f"стадия не собрана: {e}")
        return 1

    try:
        engine = pick_engine(args.engine)
    except TextEngineError as e:
        print(f"нечем писать: {e}")
        return 1

    print(f"движок: {engine.label}"
          + (f" · модель {args.model}" if args.model else ""))
    print(f"стадия: {prompt.stage.label}"
          + (f" · серия {args.episode}" if args.episode else ""))
    if prompt.outputs:
        print("ожидаются файлы: " + ", ".join(prompt.outputs))
    print("думает…")

    try:
        # Через stages.ask, а не напрямую: он же кладёт сырой ответ рядом с
        # проектом. Ответ стоит токенов, и терять его из-за неверного формата
        # или закрытой вкладки нельзя.
        answer = text_stages.ask(engine, prompt.system, prompt.user,
                                 project_dir=project_dir, stage_id=args.stage,
                                 episode=args.episode, model=args.model)
    except TextEngineError as e:
        print(f"движок отказал: {e}")
        return 1

    if not prompt.stage.outputs:
        # Питч ничего не записывает: пока вариант не выбран, записывать нечего.
        print()
        print(answer.strip())
        return 0

    try:
        files = text_stages.parse_files(answer)
        written = text_stages.write_files(
            args.stage, project_dir, files, episode=args.episode)
    except text_stages.StageError as e:
        print(f"ответ модели не разложить: {e}")
        # Ответ печатаем целиком: за него уже заплачено токенами, и терять его
        # из-за неверного формата — значит платить второй раз. Журнал панели
        # при этом ограничен, поэтому называем и файл, где ответ лежит целиком.
        draft = (project_dir / "episodes" / args.episode / text_stages.LAST_ANSWER
                 if args.episode else project_dir / text_stages.LAST_ANSWER)
        print(f"черновик ответа целиком: {draft}")
        print()
        print(answer.strip())
        return 1

    for rel in written:
        print(f"записан {rel}")
    print("готово. Одобрять артефакты — factory.py approve, "
          "status: approved стадия себе не ставит.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
