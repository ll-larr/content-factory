"""Чем писать тексты: агент на машине или модель по ключу.

Два движка, потому что у них разная цена входа. Claude Code уже стоит у того, кто
вёл проект из терминала, умеет искать в сети и знает инструменты — им и работаем,
если он есть. Тому, кому продукт отдали, ставить агента незачем: ему хватит ключа
OpenRouter, и модель он выбирает сам.

Наружу у каждого движка ровно один шов (`subprocess.run` и `_post`), поэтому тесты
не ходят в сеть и не запускают агента.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY_ENV = "OPENROUTER_API_KEY"

# Текстовая стадия — это несколько тысяч слов сценария плюс входные артефакты, а
# у познавательного жанра ещё и поиск по источникам. Часы тут не норма, но
# десятки минут — да, и обрывать их значит платить за токены и выбрасывать
# результат. Потолок был 900 с; живой прогон 2026-09-09 упёрся в него на
# исследовании получасовой серии.
DEFAULT_TIMEOUT_SECONDS = 3600

# Переменная окружения, которой потолок поднимают под конкретный прогон. Стадии
# бывают разной длины, и зашитое число однажды окажется мало любому значению;
# имя печатается в самом отказе, чтобы человек не искал его по коду.
TIMEOUT_ENV = "FACTORY_TEXT_TIMEOUT"


def timeout_seconds() -> int:
    """Сколько ждать ответа движка. Негодное значение — не повод падать."""
    return _env_seconds(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS)


# Лимит сессии — это ПАУЗА, а не отказ: он кончается сам, по времени. Поэтому
# стадия не проваливается, а ждёт и запускается снова — человек уходит, лимит
# сбрасывается, конвейер продолжает без него.
#
# Сколько всего готовы ждать за одну стадию. Шесть часов покрывают обычное окно
# сброса; ноль запрещает ожидание вовсе (нужно тем, кто хочет узнать об отказе
# сразу, и тестам).
DEFAULT_LIMIT_WAIT_SECONDS = 6 * 3600
LIMIT_WAIT_ENV = "FACTORY_LIMIT_WAIT"

# Пауза между повторами, когда время сброса из сообщения вычитать не удалось.
# Формулировку пишет чужая программа, и она может смениться — тогда работает
# слепой интервал, а не отказ.
RETRY_INTERVAL_SECONDS = 600

# Запас после названного времени сброса: попасть секунда в секунду значит
# получить тот же отказ и ждать ещё круг.
RESET_MARGIN_SECONDS = 60

# Признаки исчерпанного лимита в выводе CLI. Список открытый: чужие сообщения
# меняются, и лишний повтор дешевле проваленной стадии.
#
# «session limit» — НЕ догадка: ровно так сказал CLI живому прогону 2026-09-10
# («You've hit your session limit · resets 8pm (Europe/Moscow)»). Остальные
# написаны по догадке, и именно поэтому настоящее сообщение они не узнали —
# стадия упала как «движок отказал» вместо того, чтобы дождаться сброса.
_LIMIT_MARKERS = ("session limit", "usage limit", "limit reached",
                  "limit will reset", "rate limit", "429", "too many requests")

# Временная помеха, не связанная с лимитом: сеть, шлюз, перегрузка. Такая же
# пауза, только короткая и с потолком по числу попыток — сеть либо вернётся
# через минуту, либо лежит совсем, и ждать её часами смысла нет.
# `Connection dropped (ECONNRESET)` — с живого прогона 2026-09-10: стадия
# раскадровки работала 20 минут и умерла на нём, потеряв всё написанное.
TRANSIENT_ATTEMPTS = 3
TRANSIENT_PAUSE_SECONDS = 60
_TRANSIENT_MARKERS = ("econnreset", "connection dropped", "connection error",
                      "connection reset", "socket hang up", "etimedout",
                      "econnrefused", "bad gateway", "service unavailable",
                      "gateway timeout", "overloaded", " 502", " 503", " 504")

_RESET_HHMM = re.compile(r"reset[^\d\n]{0,40}?(\d{1,2}):(\d{2})", re.IGNORECASE)
_RESET_HOUR = re.compile(r"reset[^\d\n]{0,40}?(\d{1,2})\s*(am|pm)", re.IGNORECASE)


def _env_seconds(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def limit_wait_seconds() -> int:
    """Сколько всего готовы ждать сброса лимита за одну стадию."""
    return _env_seconds(LIMIT_WAIT_ENV, DEFAULT_LIMIT_WAIT_SECONDS)


def is_limit(said: str) -> bool:
    """Похоже ли это на исчерпанный лимит, а не на поломку."""
    low = (said or "").lower()
    return any(marker in low for marker in _LIMIT_MARKERS)


def is_transient(said: str) -> bool:
    """Помеха, которая проходит сама: сеть, шлюз, перегрузка.

    Отказ ПО СУЩЕСТВУ («нет bible/idea.md») повторять нечего — он повторится
    точно так же и только потратит время. Разделять их обязательно: иначе
    повтор либо не случается там, где он бесплатен, либо случается там, где
    бесполезен.
    """
    low = (said or "").lower()
    return any(marker in low for marker in _TRANSIENT_MARKERS)


def wait_for_limit(said: str, now: dt.datetime | None = None) -> int:
    """Сколько секунд ждать по сообщению об исчерпанном лимите.

    Claude Code называет время сброса («Your limit will reset at 15:00») —
    ждём до него, а не вслепую: слепой интервал либо будит нас рано и получает
    тот же отказ, либо держит конвейер стоящим после того, как лимит вернулся.
    Время не распозналось — работает интервал.
    """
    now = now or dt.datetime.now()
    match = _RESET_HHMM.search(said or "")
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        match = _RESET_HOUR.search(said or "")
        if not match:
            return RETRY_INTERVAL_SECONDS
        hour = int(match.group(1)) % 12
        minute = 0
        if match.group(2).lower() == "pm":
            hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return RETRY_INTERVAL_SECONDS

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Названное время уже прошло. Переносить его на завтра нельзя: CLI
        # печатает время в СВОЁЙ зоне («resets at 3pm (Europe/Moscow)»), и при
        # расхождении зон мы бы встали на сутки вместо десяти минут. Считаем,
        # что сброс либо уже был, либо вот-вот, и проверяем интервалом.
        return RETRY_INTERVAL_SECONDS
    return int((target - now).total_seconds()) + RESET_MARGIN_SECONDS


class TextEngineError(RuntimeError):
    """Движок не может выполнить запрос — и объясняет почему."""


# Сколько показать из недописанного ответа. Столько же, сколько показывает
# проверка фактов, разбирая ответ: у этих хвостов одна работа — не дать
# человеку гадать, что там происходило.
TAIL_CHARS = 400


def _tail(text) -> str:
    """Хвост того, что движок успел написать; пусто — так и скажем."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = (text or "").strip()
    if not text:
        return "Написать он ничего не успел."
    if len(text) > TAIL_CHARS:
        text = "…" + text[-TAIL_CHARS:]
    return "Вот что он успел написать:\n" + text


class TextEngine:
    """Общий интерфейс: доступен ли и как получить ответ."""

    name = ""
    label = ""

    def available(self) -> bool:
        raise NotImplementedError

    def unavailable_reason(self) -> str:
        raise NotImplementedError

    def complete(self, system: str, user: str, *, model: str | None = None,
                 effort: str | None = None) -> str:
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

    def complete(self, system: str, user: str, *, model: str | None = None,
                 effort: str | None = None) -> str:
        binary = shutil.which("claude")
        if binary is None:
            raise TextEngineError(self.unavailable_reason())

        # Системная и пользовательская части склеиваются: у headless-режима нет
        # отдельного системного канала, а разделитель модель читает как границу.
        prompt = f"{system}\n\n---\n\n{user}"
        cmd = [binary, "-p"]
        # Не выбрано — не передаём: у Claude Code на машине своя настройка, и
        # подставлять за человека значило бы решать за него молча.
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]

        waited = 0
        attempt = 0
        while True:
            done = self._run(cmd, prompt)
            if done.returncode == 0:
                return done.stdout
            said = (done.stderr or done.stdout or "").strip()

            # Помеха, которая проходит сама: сеть, шлюз, перегрузка. Ждём
            # коротко и с потолком по числу попыток — сеть либо вернётся, либо
            # лежит совсем, и ждать её часами (как лимит) смысла нет.
            if is_transient(said):
                attempt += 1
                if attempt >= TRANSIENT_ATTEMPTS:
                    raise TextEngineError(
                        f"связь рвётся: {TRANSIENT_ATTEMPTS} попытки подряд "
                        f"кончились одинаково. Сказано: {said}")
                print(f"связь оборвалась ({said}); попытка "
                      f"{attempt + 1} из {TRANSIENT_ATTEMPTS} через "
                      f"{TRANSIENT_PAUSE_SECONDS} с", flush=True)
                time.sleep(TRANSIENT_PAUSE_SECONDS)
                continue

            if not is_limit(said):
                raise TextEngineError(
                    self._explain(said)
                    or said
                    or f"claude вышел кодом {done.returncode}")

            # Лимит сессии кончается сам. Ждём и повторяем стадию целиком:
            # продолжить оборванный ответ нельзя — модель не возобновляет
            # начатое, а на нашей стороне ничего не осталось.
            allowed = limit_wait_seconds()
            pause = wait_for_limit(said)
            if waited + pause > allowed:
                raise TextEngineError(
                    f"лимит сессии исчерпан, а ждать больше нельзя: потолок "
                    f"ожидания {allowed} с (переменная {LIMIT_WAIT_ENV}, "
                    f"секунды), уже прождали {waited} с. Сказано: {said}")
            print(f"лимит сессии исчерпан: жду {pause} с и повторяю стадию "
                  f"({said})", flush=True)
            time.sleep(pause)
            waited += pause

    def _run(self, cmd: list[str], prompt: str):
        """Один запуск CLI. Шов наружу — здесь, и он один."""
        limit = timeout_seconds()
        try:
            return subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=limit)
        except subprocess.TimeoutExpired as e:
            # Процесс, проработавший четверть часа, «не запустился» — враньё, и
            # именно его человек прочитал 2026-09-09. Написанное к этому
            # моменту не выбрасываем: за него уже заплачено токенами.
            raise TextEngineError(
                f"claude не ответил за {limit} с и был прерван. Стадия может "
                f"идти дольше — подними потолок переменной {TIMEOUT_ENV} "
                f"(секунды) и запусти заново. {_tail(e.stdout)}") from None
        except (OSError, subprocess.SubprocessError) as e:
            raise TextEngineError(f"claude не запустился: {e}") from None

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
            with urllib.request.urlopen(req, timeout=timeout_seconds()) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise TextEngineError(f"OpenRouter HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, ValueError) as e:
            raise TextEngineError(f"OpenRouter недоступен: {e}") from None

    def complete(self, system: str, user: str, *, model: str | None = None,
                 effort: str | None = None) -> str:
        # `effort` здесь не при чём: это настройка Claude Code, а у OpenRouter
        # своего такого рычага в нашем запросе нет. Молча принять и не
        # использовать честнее, чем отказать: выбор относится к другому движку.
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
