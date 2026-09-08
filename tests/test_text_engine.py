"""Движки текста: Claude Code на машине или модель по ключу.

Сеть не трогается ни одним тестом: у обоих движков ровно один шов наружу, и он
подменяется.
"""
import json

import pytest

from factory.text import engine as eng


class FakeResponse:
    """Ответ OpenRouter в том виде, в каком его отдаёт chat/completions."""

    def __init__(self, text):
        self.payload = {"choices": [{"message": {"content": text}}]}


def test_claude_code_unavailable_without_binary(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    assert eng.ClaudeCodeEngine().available() is False


def test_claude_code_available_when_binary_found(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: "/usr/bin/claude")
    assert eng.ClaudeCodeEngine().available() is True


def test_claude_code_passes_prompt_and_returns_output(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs.get("input")
        return eng.subprocess.CompletedProcess(cmd, 0, stdout="готовый текст", stderr="")

    monkeypatch.setattr(eng.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(eng.subprocess, "run", fake_run)

    out = eng.ClaudeCodeEngine().complete("СИСТЕМА", "ЗАДАЧА")

    assert out == "готовый текст"
    assert "-p" in seen["cmd"]
    assert "СИСТЕМА" in seen["input"] and "ЗАДАЧА" in seen["input"]


def test_claude_code_failure_is_an_error(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: "claude")
    monkeypatch.setattr(eng.subprocess, "run",
                        lambda cmd, **kw: eng.subprocess.CompletedProcess(
                            cmd, 1, stdout="", stderr="агент не запустился"))
    with pytest.raises(eng.TextEngineError) as e:
        eng.ClaudeCodeEngine().complete("s", "u")
    assert "агент не запустился" in str(e.value)


def test_openrouter_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert eng.OpenRouterEngine().available() is False


def test_openrouter_sends_system_and_user(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    seen = {}

    def fake_post(url, payload, key):
        seen.update(url=url, payload=payload, key=key)
        return {"choices": [{"message": {"content": "ответ"}}]}

    e = eng.OpenRouterEngine()
    monkeypatch.setattr(e, "_post", fake_post)

    out = e.complete("СИСТЕМА", "ЗАДАЧА", model="anthropic/claude-opus-5")

    assert out == "ответ"
    assert seen["url"].endswith("/chat/completions")
    assert seen["payload"]["model"] == "anthropic/claude-opus-5"
    roles = {m["role"]: m["content"] for m in seen["payload"]["messages"]}
    assert roles["system"] == "СИСТЕМА"
    assert roles["user"] == "ЗАДАЧА"


def test_openrouter_requires_model(monkeypatch):
    """Модель выбирает человек: молчаливый дефолт потратил бы его деньги вслепую."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    with pytest.raises(eng.TextEngineError):
        eng.OpenRouterEngine().complete("s", "u", model=None)


def test_openrouter_empty_answer_is_an_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    e = eng.OpenRouterEngine()
    monkeypatch.setattr(e, "_post", lambda *a, **k: {"choices": []})
    with pytest.raises(eng.TextEngineError):
        e.complete("s", "u", model="x/y")


def test_pick_engine_prefers_claude_code(monkeypatch):
    """Агент умеет искать и знает инструменты — при прочих равных берём его."""
    monkeypatch.setattr(eng.shutil, "which", lambda name: "claude")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    assert eng.pick_engine().name == "claude-code"


def test_pick_engine_falls_back_to_key(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    assert eng.pick_engine().name == "openrouter"


def test_pick_engine_explains_when_nothing_available(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(eng.TextEngineError) as e:
        eng.pick_engine()
    assert "OPENROUTER_API_KEY" in str(e.value)


def test_engine_states_are_reported_for_panel(monkeypatch):
    monkeypatch.setattr(eng.shutil, "which", lambda name: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")

    states = {row["name"]: row for row in eng.engine_states()}

    assert states["claude-code"]["available"] is False
    assert states["claude-code"]["reason"]
    assert states["openrouter"]["available"] is True
