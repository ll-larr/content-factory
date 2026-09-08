"""Чего не хватает на этой машине, чтобы конвейер работал.

Продукт отдают человеку, у которого не стоит ни ffmpeg, ни node. Без этой
проверки он узнаёт о них так: нажал «Монтаж» — получил трейсбек
`FileNotFoundError: 'ffmpeg'` посреди журнала стадии, уже после оплаченной
съёмки. Отказ обязан приходить раньше и словами.

Единственное место, где записано, что нужно и зачем: список читают и панель, и
`render.py`, и оба лаунчера через сервер. Копия этого списка в трёх местах
разошлась бы в тот же день, когда появилась четвёртая зависимость.

Проверка НЕ падает и ничего не чинит: она отвечает на вопрос «что сломается» и
говорит, чем это ставится. Решение ставить — за человеком.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Сколько ждём ответа `--version`. Секунда — это уже застрявший процесс, а не
# медленная машина: нам нужен факт наличия, а не сама версия.
VERSION_TIMEOUT = 5

REQUIREMENTS: tuple[dict, ...] = (
    {
        "id": "ffmpeg",
        "label": "ffmpeg",
        "why": "мастеринг громкости, нормализация кадров в PNG, обработка голоса",
        "breaks": "монтаж эпизода и часть стадий звука",
        "install": {"windows": "winget install Gyan.FFmpeg",
                    "macos": "brew install ffmpeg",
                    "linux": "apt install ffmpeg"},
    },
    {
        "id": "node",
        "label": "Node.js",
        "why": "монтаж живёт в Remotion, а он выполняется в Node",
        "breaks": "монтаж эпизода",
        "install": {"windows": "winget install OpenJS.NodeJS.LTS",
                    "macos": "brew install node",
                    "linux": "apt install nodejs npm"},
    },
    {
        "id": "npx",
        "label": "npx",
        "why": "им запускается Remotion из montage/",
        "breaks": "монтаж эпизода",
        "install": {"windows": "ставится вместе с Node.js",
                    "macos": "ставится вместе с Node.js",
                    "linux": "ставится вместе с Node.js"},
    },
)

# Зависимости монтажа ставятся отдельной командой, и забыть её — обычное дело:
# node стоит, а `npx remotion` всё равно падает.
MONTAGE_MODULES = "montage/node_modules"
MONTAGE_INSTALL = "npm install --prefix montage"


def _version(tool: str) -> str:
    """Первая строка `<tool> --version`; пусто, если спросить не вышло.

    Версия — справка человеку, а не условие работы, поэтому любая осечка здесь
    оборачивается пустой строкой, а не отказом: инструмент найден, и этого для
    вердикта достаточно.
    """
    try:
        done = subprocess.run([tool, "--version"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=VERSION_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = (done.stdout or done.stderr or "").strip().splitlines()
    return out[0][:80] if out else ""


def check(repo_root: Path | str = Path(".")) -> list[dict]:
    """Состояние каждой зависимости: найдена ли, где, зачем нужна."""
    rows = []
    for spec in REQUIREMENTS:
        path = shutil.which(spec["id"])
        rows.append({**spec, "found": path is not None, "path": path or "",
                     "version": _version(spec["id"]) if path else ""})

    modules = Path(repo_root) / MONTAGE_MODULES
    rows.append({
        "id": "montage_modules",
        "label": "зависимости монтажа",
        "why": "Remotion и его пакеты ставятся отдельной командой",
        "breaks": "монтаж эпизода",
        "install": {os_name: MONTAGE_INSTALL
                    for os_name in ("windows", "macos", "linux")},
        "found": modules.is_dir(),
        "path": str(modules) if modules.is_dir() else "",
        "version": "",
    })
    return rows


def missing(repo_root: Path | str = Path(".")) -> list[dict]:
    return [row for row in check(repo_root) if not row["found"]]


def problems(repo_root: Path | str = Path("."), *,
             os_name: str | None = None) -> list[str]:
    """По строке на каждое отсутствующее: что сломается и чем ставится."""
    if os_name is None:
        import sys
        os_name = {"win32": "windows", "darwin": "macos"}.get(
            sys.platform, "linux")
    return [f"{row['label']} не найден — не будет работать {row['breaks']}. "
            f"Поставить: {row['install'].get(os_name, '')}".strip()
            for row in missing(repo_root)]
