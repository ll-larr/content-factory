"""Ключи провайдеров, введённые в панели.

Ключ уходит в `.env` на машине человека. Наружу — в браузер — не отдаётся никогда:
панель показывает маску и состояние, а не значение.
"""
import os
from pathlib import Path

import pytest

from factory import keys


def test_known_providers_cover_all_env_names():
    """Список провайдеров панели — тот же, что объявлен в `.env.example`.

    Сверяемся с файлом, а не со списком имён в самом тесте: раньше здесь стоял
    литерал, и новый ключ ронял тест вместо того, чтобы поймать настоящую
    рассинхронизацию. Инвариант же тут один — панель предлагает ровно те
    переменные, которые конвейер читает из окружения.
    """
    example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8")
    declared = {line.split("=", 1)[0].strip()
                for line in example.splitlines()
                if "=" in line and not line.strip().startswith("#")}
    assert {p["env"] for p in keys.PROVIDERS.values()} == declared


def test_unknown_provider_rejected(tmp_path):
    """Имя провайдера приходит из браузера и в файл без проверки не попадает."""
    with pytest.raises(KeyError):
        keys.write_key(tmp_path, "НеПровайдер", "x")


def test_writes_new_line_and_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    keys.write_key(tmp_path, "Runware", "rw-secret-9999")

    assert "RUNWARE_API_KEY=rw-secret-9999" in (tmp_path / ".env").read_text("utf-8")
    # Ключ должен работать сразу, без перезапуска панели.
    assert os.environ["RUNWARE_API_KEY"] == "rw-secret-9999"


def test_replaces_existing_line_without_duplicating(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)
    (tmp_path / ".env").write_text("RUNWARE_API_KEY=старый\n", encoding="utf-8")

    keys.write_key(tmp_path, "Runware", "новый-1234")

    body = (tmp_path / ".env").read_text("utf-8")
    assert body.count("RUNWARE_API_KEY") == 1
    assert "новый-1234" in body
    assert "старый" not in body


def test_keeps_other_lines_and_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "# мой комментарий\nWAVESPEED_API_KEY=ws-1\n\n", encoding="utf-8")

    keys.write_key(tmp_path, "Runware", "rw-2222")

    body = (tmp_path / ".env").read_text("utf-8")
    assert "# мой комментарий" in body
    assert "WAVESPEED_API_KEY=ws-1" in body
    assert "RUNWARE_API_KEY=rw-2222" in body


def test_value_with_newline_rejected(tmp_path):
    """Перевод строки в значении дописал бы в .env чужую переменную."""
    with pytest.raises(ValueError):
        keys.write_key(tmp_path, "Runware", "a\nWAVESPEED_API_KEY=подделка")


def test_blank_value_rejected(tmp_path):
    with pytest.raises(ValueError):
        keys.write_key(tmp_path, "Runware", "   ")


def test_state_never_returns_value(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNWARE_API_KEY", "rw-очень-секретный-хвост")
    monkeypatch.delenv("WAVESPEED_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    state = {row["provider"]: row for row in keys.read_state(tmp_path)}

    dump = repr(state)
    assert "очень-секретный" not in dump
    assert state["Runware"]["set"] is True
    assert state["Runware"]["mask"].endswith("вост")
    assert state["WaveSpeed"]["set"] is False
    assert state["WaveSpeed"]["mask"] is None


def test_state_reports_roles_for_every_provider(tmp_path):
    for row in keys.read_state(tmp_path):
        assert row["roles"], row


def test_mask_shows_four_last_chars():
    assert keys.mask("abcdefgh1234").endswith("1234")
    assert "abcdefgh" not in keys.mask("abcdefgh1234")


def test_mask_of_short_value_reveals_nothing():
    """Короткий ключ нельзя показать «последними четырьмя» целиком."""
    assert keys.mask("abc") == "•" * len("abc")


@pytest.mark.skipif(os.name == "nt", reason="права файла проверяются на POSIX")
def test_file_mode_is_0600_on_posix(tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)

    keys.write_key(tmp_path, "Runware", "rw-3333")

    assert oct((tmp_path / ".env").stat().st_mode & 0o777) == "0o600"
