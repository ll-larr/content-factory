"""Адаптер Higgsfield CLI.

Единственное место в кодовой базе, где прописаны точные субкоманды и флаги
CLI-бинаря ``higgsfield``. Источник правды — ``knowledge/higgsfield-cli.md``
(результат живого спайка 2026-06-12, CLI 0.1.40).

Статусы задач и формат ответов из спайка 2026-06-12:
  - ``in_progress`` → ``completed`` (терминальные: ``completed``, ``failed``).
  - ``generate cost`` → ``{"credits": N, "credits_exact": N.N}``
  - ``generate create`` → ``["<job_id>", ...]``  (МАССИВ)
  - ``generate get`` → ``{"id": ..., "status": ..., "result_url": ..., ...}``

Субкоманды download нет — результат качается HTTP-ом по result_url.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# Имя бинаря. На Windows shutil.which найдёт higgsfield.cmd через PATHEXT.
_CLI_NAME = "higgsfield"


class HiggsfieldError(RuntimeError):
    """Ошибка при работе с Higgsfield CLI или результатами вызова."""


def _cli_binary() -> str:
    """Вернуть полный путь к бинарю CLI (или голое имя как фолбэк)."""
    found = shutil.which(_CLI_NAME)
    return found if found else _CLI_NAME


def _params_to_flags(params: dict) -> list[str]:
    """Преобразовать словарь параметров в список флагов CLI.

    Правила (из спайка):
    - ``refs`` (список путей) → повторяющийся флаг ``--image <path>`` на каждый;
    - ``start_frame`` → ``--start-image <path>``;
    - ``end_frame`` → ``--end-image <path>``;
    - остальные ключи → ``--<key> <str(value)>``.
    """
    flags: list[str] = []
    for key, value in params.items():
        if key == "refs":
            if not value:
                continue
            for path in value:
                flags.extend(["--image", str(path)])
        elif key == "start_frame":
            flags.extend(["--start-image", str(value)])
        elif key == "end_frame":
            flags.extend(["--end-image", str(value)])
        else:
            flags.extend([f"--{key}", str(value)])
    return flags


def _run(args: list[str]) -> str:
    """Выполнить команду CLI и вернуть stdout.

    Нулевой код возврата → вернуть stdout.
    Ненулевой → HiggsfieldError с командой и stderr.
    """
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise HiggsfieldError(
            f"Команда {args!r} завершилась с кодом {result.returncode}: {result.stderr}"
        )
    return result.stdout


def _parse_json(stdout: str) -> dict | list:
    """Разобрать JSON из stdout; нечитаемый вывод → {'raw': stdout}."""
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw": stdout}


def _fetch(url: str, dest: str) -> None:
    """Скачать файл по HTTP и сохранить в dest (urllib.request)."""
    urllib.request.urlretrieve(url, dest)


# ---------------------------------------------------------------------------
# Публичный интерфейс (используется Task 9 generate_batch.py)
# ---------------------------------------------------------------------------

def estimate(model: str, params: dict) -> float:
    """Рассчитать смету в кредитах — БЕСПЛАТНО, без генерации.

    Вызывает ``higgsfield generate cost <model> [--флаги] --json``.
    Возвращает ``credits_exact`` (точное число), фолбэк на ``credits``.

    Поднимает HiggsfieldError если ответ не содержит ожидаемых полей.
    """
    cli = _cli_binary()
    args = [cli, "generate", "cost", model] + _params_to_flags(params) + ["--json"]
    stdout = _run(args)
    data = _parse_json(stdout)
    if not isinstance(data, dict):
        raise HiggsfieldError(f"Неожиданный формат ответа generate cost: {stdout!r}")
    if "credits_exact" in data:
        return float(data["credits_exact"])
    if "credits" in data:
        return float(data["credits"])
    raise HiggsfieldError(f"Ответ generate cost не содержит поля credits: {data!r}")


def submit(model: str, params: dict) -> str:
    """Создать задачу генерации и вернуть job_id.

    Вызывает ``higgsfield generate create <model> [--флаги] --json``.
    CLI возвращает МАССИВ job_id; берём первый элемент.

    Поднимает HiggsfieldError при пустом массиве или неверном формате.
    """
    cli = _cli_binary()
    args = [cli, "generate", "create", model] + _params_to_flags(params) + ["--json"]
    stdout = _run(args)
    data = _parse_json(stdout)
    if not isinstance(data, list):
        raise HiggsfieldError(f"generate create вернул не массив: {stdout!r}")
    if not data:
        raise HiggsfieldError("generate create вернул пустой массив job_id")
    return str(data[0])


def poll(job_id: str) -> dict:
    """Получить текущий статус задачи без ожидания.

    Вызывает ``higgsfield generate get <job_id> --json``.
    Возвращает dict (или {'raw': stdout} если ответ не JSON).
    """
    cli = _cli_binary()
    args = [cli, "generate", "get", job_id, "--json"]
    stdout = _run(args)
    result = _parse_json(stdout)
    if isinstance(result, dict):
        return result
    return {"raw": stdout}


def wait(
    job_id: str,
    timeout_sec: int = 1800,
    interval_sec: int = 10,
) -> dict:
    """Ждать терминального статуса задачи.

    Опрашивает poll() каждые ``interval_sec`` секунд до ``timeout_sec``.
    Терминальные статусы: ``completed``, ``failed`` (и любой не ``in_progress``).

    Поднимает HiggsfieldError при истечении timeout.
    """
    deadline = time.monotonic() + timeout_sec
    while True:
        result = poll(job_id)
        status = result.get("status", "")
        if status != "in_progress":
            return result
        if time.monotonic() >= deadline:
            raise HiggsfieldError(
                f"Timeout {timeout_sec}s истёк ожидая завершения задачи {job_id!r}"
            )
        time.sleep(interval_sec)


def download(job_id: str, dest: Path) -> Path:
    """Скачать результат завершённой задачи по HTTP.

    Берёт ``result_url`` из poll(); требует status=completed и непустой URL.
    Создаёт родительские директории, скачивает файл, проверяет наличие на диске.

    Поднимает HiggsfieldError если задача не завершена, URL пуст или файл не появился.
    """
    dest = Path(dest)
    status_data = poll(job_id)
    status = status_data.get("status", "")
    result_url = status_data.get("result_url", "")

    if status != "completed" or not result_url:
        raise HiggsfieldError(
            f"Задача {job_id!r} не готова к скачиванию: status={status!r}, "
            f"result_url={result_url!r}"
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    _fetch(result_url, str(dest))

    if not dest.exists():
        raise HiggsfieldError(
            f"Файл после скачивания missing: {dest}"
        )
    return dest
