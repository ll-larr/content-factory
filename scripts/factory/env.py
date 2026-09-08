"""Ключи из `.env` рядом с корнем репозитория.

Зачем файл, если ключи и так читаются из окружения (`providers/base.py`): на чужой
машине переменные окружения задаются диалогом в панели управления Windows либо
правкой профиля оболочки, и человек спотыкается об это раньше, чем доходит до
первой генерации. `.env` в `.gitignore`, поэтому в репозиторий он не уедет.

Окружение сильнее файла. Разовый запуск с другим ключом (`KEY=... python ...`)
должен работать, а не молча съедаться файлом: иначе генерация оплачивается не тем
счётом, чем думал человек.

Своего парсера здесь ровно столько, сколько нужно для списка `KEY=значение`:
внешней зависимости (`python-dotenv`) ради восьми строк не заводим — весь проект
держится на стандартной библиотеке.
"""
from __future__ import annotations

import os
from pathlib import Path

FILENAME = ".env"


def load_env(root: Path | str = Path(".")) -> list[str]:
    """Подставить недостающие переменные из `<root>/.env`.

    Возвращает имена переменных, которые ДЕЙСТВИТЕЛЬНО были заданы этим вызовом,
    чтобы вызывающий мог сказать человеку, откуда взялся ключ. Отсутствие файла —
    обычный случай (ключи заданы в окружении), а не ошибка.
    """
    path = Path(root) / FILENAME
    if not path.is_file():
        return []

    # utf-8-sig: Блокнот на Windows пишет BOM, и без этого первое имя переменной
    # получило бы невидимый префикс — ключ «есть», но не находится.
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return []

    applied: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]

        name, _, value = line.partition("=")       # режем по ПЕРВОМУ «=»
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        # Пустое значение — строка шаблона из .env.example. Подставлять её значит
        # выдать «ключ задан» там, где его нет.
        if not name or not value or os.environ.get(name):
            continue

        os.environ[name] = value
        applied.append(name)
    return applied
