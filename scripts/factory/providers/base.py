"""Базовый слой провайдеров: общий HTTP-плмбинг + протоколы поверхностей.

Точные эндпоинты/пейлоады/model-id каждого провайдера живут ТОЛЬКО в его адаптере
и его knowledge-доке (правило CLAUDE.md). Здесь — только провайдеро-НЕзависимое:
протоколы поверхностей, базовое исключение, urllib-обёртки, цикл ожидания (wait) и
атомарное скачивание (download). Смета считается из карточки (estimate_media_cost).

Поверхностей две и они не пересекаются: ``VideoProvider`` производит медиа за
деньги по карточке модели, ``SearchProvider`` ищет в вебе для проверки фактов.
Общее у них — только ключ и один POST (``KeyedHTTPClient``).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from factory.models import estimate_media_cost, find_card


class ProviderError(RuntimeError):
    """Ошибка работы с провайдером генерации (сеть, контракт, конфиг)."""


@runtime_checkable
class VideoProvider(Protocol):
    """Поверхность, унаследованная от Higgsfield-адаптера (FINAL §5.1)."""
    unit: str

    def preflight_problems(self, model: str, params: dict) -> list[str]: ...
    def estimate(self, model: str, params: dict) -> float: ...
    def submit(self, model: str, params: dict) -> str: ...
    def poll(self, job_id: str) -> dict: ...
    def wait(self, job_id: str, timeout_sec: int = ...,
             interval_sec: int = ...) -> dict: ...
    def download(self, job_id: str, dest: Path) -> Path: ...


class KeyedHTTPClient:
    """Ключ из окружения и единственный сетевой шов — общее для всех провайдеров.

    Выделено из ``BaseHTTPProvider``, когда появился провайдер поиска: у него нет
    ни карточек моделей, ни сабмита с опросом, ни скачивания — только ключ и один
    POST. Наследовать ради этого всю видеоповерхность значило бы объявить у
    поиска методы ``submit``/``wait``/``download``, которых у него нет.
    """
    name: str = ""
    api_key_env: str = ""

    def _missing_key(self) -> bool:
        """Объявлен ли ключ и отсутствует ли он в окружении.

        Пустое ``api_key_env`` означает «ключ не нужен», а не «ключ под пустым
        именем»: провайдер, который его не объявил, не должен требовать
        переменных окружения.
        """
        return bool(self.api_key_env) and not os.environ.get(self.api_key_env)

    def _no_key_message(self) -> str:
        return f"{self.name}: переменная окружения {self.api_key_env} не задана"

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(self._no_key_message())
        return key

    # ---- HTTP-обёртка (единственный сетевой шов) ----
    def _request(self, method: str, url: str, *, json_body=None) -> dict:
        headers = {"Authorization": f"Bearer {self._key()}",
                   "Content-Type": "application/json"}
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise ProviderError(
                f"{self.name}: HTTP {e.code} на {url}: {body}") from None
        except urllib.error.URLError as e:
            raise ProviderError(
                f"{self.name}: сетевая ошибка на {url}: {e.reason}") from None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}


class BaseHTTPProvider(KeyedHTTPClient):
    """Общая реализация поверх REST: estimate/wait/download + urllib-обёртки.

    Подклассы задают ``name``/``api_key_env`` и реализуют ``submit``, ``poll``,
    ``_status(result)`` (нормализованный статус) и ``_result_url(result)``.
    Единственный сетевой шов — ``_request`` и ``_download_file`` (мокаются в тестах).
    """
    unit: str = "$"
    # Умеет ли провайдер отдать остаток на счету. По умолчанию нет: панель
    # покажет прочерк, и это честнее выдуманного числа — по балансу человек
    # решает, хватит ли денег на съёмку.
    supports_balance: bool = False
    # Не-терминальные статусы (продолжаем опрос).
    _POLLING = {"", "created", "queued", "pending", "processing",
                "in_progress", "running", "starting"}
    # Терминальные статусы провала.
    _FAILED = {"failed", "error", "cancelled", "canceled", "expired"}

    def __init__(self, knowledge_dir: Path | str = Path("knowledge")):
        self.knowledge_dir = Path(knowledge_dir)

    # ---- конфиг / карточки ----
    def _card(self, model: str) -> dict:
        return find_card(self.knowledge_dir, model)

    def _pv(self, card: dict) -> dict:
        pv = (card.get("providers") or {}).get(self.name)
        if pv is None:
            raise ProviderError(
                f"{card.get('id')}: не сконфигурирован для провайдера {self.name!r}")
        return pv

    def _concrete_id(self, card: dict, tier: str | None) -> str:
        """Конкретный model-id/path провайдера под выбранный тир."""
        pv = self._pv(card)
        if "tiers" in pv:
            chosen = tier or pv.get("default_tier")
            if chosen not in pv["tiers"]:
                raise ProviderError(
                    f"{card.get('id')}: неизвестный tier {chosen!r} для {self.name}")
            return pv["tiers"][chosen]["id"]
        if "id" not in pv:
            raise ProviderError(f"{card.get('id')}: нет id для провайдера {self.name}")
        return pv["id"]

    @staticmethod
    def _media(value: str) -> str:
        """http(s)-URL или data-URI пропускаем как есть; локальный путь кодируем
        в data-URI base64 (провайдеры принимают URL или data-URI)."""
        if value.startswith(("http://", "https://", "data:")):
            return value
        path = Path(value)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    # ---- скачивание (второй сетевой шов) ----
    def _download_file(self, url: str, dest: str) -> None:
        urllib.request.urlretrieve(url, dest)

    # ---- баланс ----
    def balance(self) -> float:
        """Остаток на счету провайдера в долларах.

        Реализуют только те, у кого эндпоинт известен и проверен живьём. У
        остальных вызов — ошибка, а не ноль: ноль на экране означал бы «денег
        нет», хотя на деле мы просто не умеем спросить.
        """
        raise ProviderError(f"{self.name}: баланс через API недоступен")

    @staticmethod
    def _find_balance(payload: dict) -> float:
        """Достать число баланса из ответа провайдера.

        Ответ смотрели живьём один раз, и форма может отличаться между версиями
        API, поэтому число ищется и на верхнем уровне, и во вложенном `data`.
        Отсутствие числа — ошибка: молча вернуть 0 значит соврать про деньги.
        """
        for scope in (payload, payload.get("data") or {}):
            if isinstance(scope, dict) and "balance" in scope:
                try:
                    return float(scope["balance"])
                except (TypeError, ValueError):
                    break
        raise ProviderError(f"в ответе нет числового поля balance: {payload}")

    # ---- общая поверхность ----
    def preflight_problems(self, model: str, params: dict) -> list[str]:
        """Всё, что мешает выполнить вызов, — ДО сметы и трат (ревью-находка:
        смета не должна обещать цену, которую submit не может выполнить).

        Здесь живёт только провайдеро-НЕзависимая часть: отсутствие ключа. Это
        ошибка конфигурации, известная до первого байта в сеть, и раньше она
        всплывала лениво в ``_key()`` на сабмите — по строке на каждую единицу
        батча, уже после показа сметы и подтверждения траты (D-2 первого живого
        прогона). Проверять её в generate_batch.py нельзя: имя переменной знает
        только адаптер (изоляция провайдера — правило CLAUDE.md).

        Метод НЕ переопределяют: свои ограничения адаптер объявляет в
        ``_provider_preflight`` — иначе адаптер, забывший вызвать super(),
        молча отключил бы проверку ключа.
        """
        problems = [self._no_key_message()] if self._missing_key() else []
        return problems + self._provider_preflight(model, params)

    def _provider_preflight(self, model: str, params: dict) -> list[str]:
        """Хук адаптера: какие resolution/тиры/etc он реально умеет.

        Специфика провайдера живёт ТОЛЬКО в адаптере — правило изоляции
        провайдера (CLAUDE.md). По умолчанию проверять нечего — пустой список
        (см. RunwareProvider).
        """
        return []

    def estimate(self, model: str, params: dict) -> float:
        card = self._card(model)
        return estimate_media_cost(
            card, self.name, params.get("resolution", "720p"),
            params.get("duration", 0), params.get("tier"))

    def _status(self, result: dict) -> str:
        raise NotImplementedError

    def _result_url(self, result: dict) -> str:
        raise NotImplementedError

    def submit(self, model: str, params: dict) -> str:
        raise NotImplementedError

    def poll(self, job_id: str) -> dict:
        raise NotImplementedError

    def wait(self, job_id: str, timeout_sec: int = 1800,
             interval_sec: int = 10) -> dict:
        deadline = time.monotonic() + timeout_sec
        while True:
            result = self.poll(job_id)
            if self._status(result) not in self._POLLING:
                return result
            if time.monotonic() >= deadline:
                raise ProviderError(
                    f"{self.name}: timeout {timeout_sec}s ожидая задачу {job_id!r}")
            time.sleep(min(interval_sec, max(0.0, deadline - time.monotonic())))

    def download(self, job_id: str, dest: Path) -> Path:
        dest = Path(dest)
        result = self.poll(job_id)
        status = self._status(result)
        if status in self._FAILED:
            raise ProviderError(
                f"{self.name}: задача {job_id!r} завершилась статусом {status!r} — "
                "требуется перегенерация")
        url = self._result_url(result)
        if not url:
            raise ProviderError(
                f"{self.name}: задача {job_id!r} без результата (status={status!r})")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        try:
            self._download_file(url, str(tmp))
            os.replace(tmp, dest)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        if not dest.exists():
            raise ProviderError(f"{self.name}: файл после скачивания missing: {dest}")
        return dest


@runtime_checkable
class SearchProvider(Protocol):
    """Поверхность поиска в вебе. Нужна ПРОВЕРКЕ ФАКТОВ, а не генерации.

    Отдельный протокол, а не метод у ``VideoProvider``: поиск не производит
    медиа, не стоит денег провайдера генерации и не проходит через карточку
    модели. Смешать их значило бы обещать `search` каждому адаптеру видео.
    """
    name: str
    supports_search: bool

    def available(self) -> bool: ...
    def unavailable_reason(self) -> str: ...
    def search(self, query: str, *, max_results: int = ...) -> list[dict]: ...


class BaseSearchProvider(KeyedHTTPClient):
    """Общее для поисковых провайдеров: ключ, доступность, форма результата.

    Наружу каждый результат приводится к четырём полям — `title`, `url`,
    `snippet`, `score`. Промпт проверяющего собирается из них, и провайдеро-
    специфичные поля туда не уезжают: иначе смена поисковика молча поменяла бы
    то, что читает проверяющий.
    """
    supports_search: bool = True

    def available(self) -> bool:
        return not self._missing_key()

    def unavailable_reason(self) -> str:
        return self._no_key_message()

    def search(self, query: str, *, max_results: int = 8) -> list[dict]:
        raise NotImplementedError
