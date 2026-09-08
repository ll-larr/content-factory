"""Загрузка ключей из .env.

Файл нужен ради установки на чужой машине: системные переменные окружения на
Windows правятся через диалог в панели управления, и человек, поставивший
конвейер, спотыкается об это раньше, чем доходит до первой генерации.
"""
import os

import pytest

from factory.env import load_env


def test_missing_file_is_not_an_error(tmp_path):
    """Нет .env — нет и переменных: это обычный случай, а не сбой."""
    assert load_env(tmp_path) == []


def test_reads_pairs(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("WAVESPEED_API_KEY=abc123\n", encoding="utf-8")
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)

    assert load_env(tmp_path) == ["WAVESPEED_API_KEY"]
    assert os.environ["WAVESPEED_API_KEY"] == "abc123"


def test_environment_wins_over_file(tmp_path, monkeypatch):
    """Уже заданное окружение сильнее файла.

    Иначе разовый запуск с другим ключом (`KEY=... python ...`) молча съедался бы
    файлом, и человек оплачивал бы генерацию не тем счётом, чем думал.
    """
    (tmp_path / ".env").write_text("RUNWARE_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("RUNWARE_API_KEY", "from-shell")

    assert load_env(tmp_path) == []
    assert os.environ["RUNWARE_API_KEY"] == "from-shell"


def test_skips_comments_blanks_and_empty_values(tmp_path, monkeypatch):
    """Пустое значение — это строка шаблона .env.example, а не заданный ключ."""
    (tmp_path / ".env").write_text(
        "# комментарий\n"
        "\n"
        "OPENROUTER_API_KEY=\n"
        "   \n"
        "RUNWARE_API_KEY=live\n",
        encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    assert load_env(tmp_path) == ["RUNWARE_API_KEY"]
    assert "OPENROUTER_API_KEY" not in os.environ


def test_strips_quotes_export_and_spaces(tmp_path, monkeypatch):
    """Форматы, которые человек напишет по привычке из shell-скриптов."""
    (tmp_path / ".env").write_text(
        'export WAVESPEED_API_KEY = "ws-quoted"\n'
        "RUNWARE_API_KEY='rw-single'\n",
        encoding="utf-8")
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    load_env(tmp_path)
    assert os.environ["WAVESPEED_API_KEY"] == "ws-quoted"
    assert os.environ["RUNWARE_API_KEY"] == "rw-single"


def test_ignores_broken_lines(tmp_path, monkeypatch):
    """Строка без `=` — мусор, но не повод уронить запуск конвейера."""
    (tmp_path / ".env").write_text(
        "просто текст\n"
        "=без-имени\n"
        "RUNWARE_API_KEY=ok\n",
        encoding="utf-8")
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    assert load_env(tmp_path) == ["RUNWARE_API_KEY"]


def test_reads_utf8_with_bom(tmp_path, monkeypatch):
    """Блокнот на Windows пишет BOM, и первый ключ иначе получил бы имя с ﻿."""
    (tmp_path / ".env").write_bytes("RUNWARE_API_KEY=bom\n".encode("utf-8-sig"))
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    assert load_env(tmp_path) == ["RUNWARE_API_KEY"]
    assert os.environ["RUNWARE_API_KEY"] == "bom"


def test_value_with_equals_survives(tmp_path, monkeypatch):
    """Знак `=` внутри ключа провайдера — не разделитель: режем по первому."""
    (tmp_path / ".env").write_text("WAVESPEED_API_KEY=a=b=c\n", encoding="utf-8")
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)

    load_env(tmp_path)
    assert os.environ["WAVESPEED_API_KEY"] == "a=b=c"
