"""Чем писать тексты: агент на машине или модель по ключу.

Два движка, потому что у них разная цена входа. Claude Code уже стоит у того, кто
вёл проект из терминала, умеет искать в сети и знает инструменты — им и работаем,
если он есть. Тому, кому продукт отдали, ставить агента незачем: ему хватит ключа
OpenRouter, и модель он выбирает сам.

Наружу у каждого движка ровно один шов (`subprocess.run` и `_post`), поэтому тесты
не ходят в сеть и не запускают агента.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPENROUTER_API_KEY"

# Текстовая стадия — это несколько тысяч слов сценария плюс входные артефакты.
# Минуты ожидания здесь норма, и обрывать их по короткому таймауту значит платить
# за токены и выбрасывать результат.
TIMEOUT_SECONDS = 900


class TextEngineError(RuntimeError):
    """Движок не может выполнить запрос — и объясняет почему."""


class TextEngine:
    """Общий интерфейс: доступен ли и как получить ответ."""

    name = ""
    label = ""

    def available(self) -> bool:
        raise NotImplementedError

    def unavailable_reason(self) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        raise NotImplementedError


# Признаки того, что CLI не смог аутентифицироваться. Ловим их, чтобы человек
# получил не сырой ответ чужой программы, а то, что с этим делать: сообщения
# вида «API Error: 401 OAuth access token has been revoked» или «403 Request
# not allowed» не говорят ни про `claude auth login`, ни про второй движок.
_AUTH_MARKERS = ("failed to authenticate", "oauth", "api error: 401",
                 "api error: 403", "unauthorized", "not allowed")


class ClaudeCodeEngine(TextEngine):
    """Агент на этой машине. Умеет искать в сети — важно для проверки фактов."""

    name = "claude-code"
    label = "Claude Code на этой машине"

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def unavailable_reason(self) -> str:
        return ("claude не найден в PATH; поставь Claude Code или задай "
                f"{API_KEY_ENV}")

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        binary = shutil.which("claude")
        if binary is None:
            raise TextEngineError(self.unavailable_reason())

        # Системная и пользовательская части склеиваются: у headless-режима нет
        # отдельного системного канала, а разделитель модель читает как границу.
        prompt = f"{system}\n\n---\n\n{user}"
        cmd = [binary, "-p"]
        if model:
            cmd += ["--model", model]

        try:
            done = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError) as e:
            raise TextEngineError(f"claude не запустился: {e}") from None

        if done.returncode != 0:
            said = (done.stderr or done.stdout or "").strip()
            raise TextEngineError(
                self._explain(said)
                or said
                or f"claude вышел кодом {done.returncode}")
        return done.stdout

    @staticmethod
    def _explain(said: str) -> str:
        """Отказ аутентификации — словами и с лекарством; иначе пусто.

        `claude auth status` на такой поломке отвечает `loggedIn: true`
        (проверено 2026-09-08), то есть спросить состояние заранее нельзя:
        единственный честный сигнал — сам отказавший вызов. Поэтому объясняем
        здесь, а не гасим движок в `available()`.
        """
        low = said.lower()
        if not any(marker in low for marker in _AUTH_MARKERS):
            return ""
        return (f"Claude Code не авторизован ({said}). "
                "Почини одним из двух: выполни `claude auth login` в терминале "
                "(команда открывает браузер, поэтому из панели её не запустить) "
                f"— либо переключись на второй движок: задай {API_KEY_ENV} во "
                "вкладке «Ключи» и выбери модель по ключу.")


class OpenRouterEngine(TextEngine):
    """Модель по ключу. Какую именно — решает человек, а не код."""

    name = "openrouter"
    label = "Модель по ключу OpenRouter"

    def available(self) -> bool:
        return bool(os.environ.get(API_KEY_ENV))

    def unavailable_reason(self) -> str:
        return f"переменная {API_KEY_ENV} не задана"

    def _post(self, url: str, payload: dict, key: str) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     # OpenRouter просит назвать приложение; без этого запрос
                     # проходит, но в их статистике проект безымянный.
                     "X-Title": "content-factory"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise TextEngineError(f"OpenRouter HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, ValueError) as e:
            raise TextEngineError(f"OpenRouter недоступен: {e}") from None

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise TextEngineError(self.unavailable_reason())
        if not model:
            # Молчаливый дефолт потратил бы деньги человека на модель, которую он
            # не выбирал, а цены отличаются в пятьдесят раз.
            raise TextEngineError("модель не выбрана: укажи её в панели")

        data = self._post(OPENROUTER_URL, {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, key)

        choices = data.get("choices") or []
        if not choices:
            raise TextEngineError(f"пустой ответ модели: {data}")
        return choices[0].get("message", {}).get("content", "")


ENGINES = (ClaudeCodeEngine, OpenRouterEngine)


def engine_states() -> list[dict]:
    """Что доступно на этой машине — для показа в панели."""
    rows = []
    for cls in ENGINES:
        engine = cls()
        ok = engine.available()
        rows.append({"name": engine.name, "label": engine.label,
                     "available": ok,
                     "reason": "" if ok else engine.unavailable_reason()})
    return rows


def pick_engine(preferred: str | None = None) -> TextEngine:
    """Движок для работы. Агент предпочтительнее: он умеет искать и читать файлы."""
    candidates = [cls() for cls in ENGINES]
    if preferred:
        chosen = [e for e in candidates if e.name == preferred]
        if not chosen:
            raise TextEngineError(f"неизвестный движок {preferred!r}")
        if not chosen[0].available():
            raise TextEngineError(chosen[0].unavailable_reason())
        return chosen[0]

    for engine in candidates:
        if engine.available():
            return engine
    raise TextEngineError(
        "нечем писать тексты: claude не найден в PATH и "
        f"{API_KEY_ENV} не задан")
