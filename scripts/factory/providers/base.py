"""Базовый слой провайдеров: общий HTTP-плмбинг + протокол VideoProvider.

Точные эндпоинты/пейлоады/model-id каждого провайдера живут ТОЛЬКО в его адаптере
и его knowledge-доке (правило CLAUDE.md). Здесь — только провайдеро-НЕзависимое:
протокол поверхности, базовое исключение, urllib-обёртки, цикл ожидания (wait) и
атомарное скачивание (download). Смета считается из карточки (estimate_media_cost).
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


class BaseHTTPProvider:
    """Общая реализация поверх REST: estimate/wait/download + urllib-обёртки.

    Подклассы задают ``name``/``api_key_env`` и реализуют ``submit``, ``poll``,
    ``_status(result)`` (нормализованный статус) и ``_result_url(result)``.
    Единственный сетевой шов — ``_request`` и ``_download_file`` (мокаются в тестах).
    """
    name: str = ""
    unit: str = "$"
    api_key_env: str = ""
    # Не-терминальные статусы (продолжаем опрос).
    _POLLING = {"", "created", "queued", "pending", "processing",
                "in_progress", "running", "starting"}
    # Терминальные статусы провала.
    _FAILED = {"failed", "error", "cancelled", "canceled", "expired"}

    def __init__(self, knowledge_dir: Path | str = Path("knowledge")):
        self.knowledge_dir = Path(knowledge_dir)

    # ---- конфиг / карточки ----
    def _key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(
                f"{self.name}: переменная окружения {self.api_key_env} не задана")
        return key

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

    # ---- HTTP-обёртки (единственный сетевой шов) ----
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

    def _download_file(self, url: str, dest: str) -> None:
        urllib.request.urlretrieve(url, dest)

    # ---- общая поверхность ----
    def preflight_problems(self, model: str, params: dict) -> list[str]:
        """Хук: проверка параметров вызова ДО сметы и трат (ревью-находка:
        смета не должна обещать цену, которую submit не может выполнить).

        Специфика провайдера (какие resolution/тиры/etc он реально умеет)
        живёт ТОЛЬКО в адаптере — правило изоляции провайдера (CLAUDE.md).
        По умолчанию проверять нечего — пустой список; переопределяется в
        адаптере, знающем свои ограничения (см. RunwareProvider).
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
