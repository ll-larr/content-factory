"""Пакет конвейера.

Здесь же — единственная проверка окружения. Каждая точка входа импортирует
что-нибудь из `factory.*`, поэтому проверка стоит один раз и работает для всех
скриптов сразу.

Зачем она. Зависимости проекта живут в `.venv`, а человек естественно набирает
`python scripts/serve.py`. Системный интерпретатор падает на `import yaml`
трейсбеком, который говорит о чём угодно, кроме главного: взят не тот python.
Сообщение ниже говорит именно это и даёт готовую команду.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml  # noqa: F401
except ModuleNotFoundError as e:  # pragma: no cover — проверяется живым запуском
    # Консоль Windows по умолчанию не в UTF-8, и подсказка на русском вышла бы
    # мусором ровно в тот момент, когда её надо прочитать. Переключаем ДО того,
    # как исключение уйдёт наверх: трейсбек печатает уже интерпретатор.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    _root = Path(__file__).resolve().parents[2]
    _venv = _root / ".venv" / ("Scripts" if sys.platform == "win32" else "bin")
    _python = _venv / ("python.exe" if sys.platform == "win32" else "python")
    _hint = (
        f"\nНе найден пакет {e.name!r}.\n\n"
        f"Скорее всего, взят системный python вместо окружения проекта.\n"
        f"Текущий: {sys.executable}\n"
    )
    if _python.exists():
        _hint += (f"Нужный:   {_python}\n\n"
                  f"Запускай так:\n"
                  f"  {_python} {' '.join(sys.argv) or '<скрипт>'}\n")
    else:
        _hint += ("\nОкружения нет — создай его:\n"
                  "  python -m venv .venv\n"
                  f"  {_python} -m pip install -r requirements.txt\n")
    raise ModuleNotFoundError(_hint) from None
