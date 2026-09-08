"""Ключи провайдеров: состояние для панели и запись в `.env`.

Панель — единственный интерфейс продукта, значит и ключи вводятся в ней. Файл
`.env` лежит на машине человека и в `.gitignore`; никуда, кроме самого провайдера
в момент генерации, ключ не уезжает.

Наружу значение не отдаётся НИКОГДА. Панель показывает маску и состояние: этого
хватает, чтобы понять «ключ на месте» или «ключ не тот», и не хватает, чтобы
утащить ключ из вкладки, оставленной открытой.

Читает этот файл `factory/env.py`, поэтому сюда не должно попасть ничего, что
пришло из браузера без проверки: ни чужое имя переменной, ни перевод строки внутри
значения — иначе одно поле ввода дописало бы в `.env` вторую переменную.
"""
from __future__ import annotations

import os
from pathlib import Path

FILENAME = ".env"

# Провайдеры, которые панель предлагает настроить, и за что каждый отвечает.
# Список закрытый: имя приходит из браузера и должно совпасть с одним из этих.
PROVIDERS: dict[str, dict] = {
    "WaveSpeed": {"env": "WAVESPEED_API_KEY",
                  "roles": "речь · эффекты · музыка · липсинк"},
    "Runware": {"env": "RUNWARE_API_KEY",
                "roles": "кадры · отрезки"},
    "OpenRouter": {"env": "OPENROUTER_API_KEY",
                   "roles": "кадры · отрезки · текстовые стадии"},
    "Tavily": {"env": "TAVILY_API_KEY",
               "roles": "поиск для проверки фактов"},
}

VISIBLE_TAIL = 4


def mask(value: str) -> str:
    """Маска ключа: точки и четыре последних символа.

    У короткой строки хвост не показываем вовсе: четыре символа из шести — это
    уже не маска, а подсказка.
    """
    if len(value) <= VISIBLE_TAIL * 2:
        return "•" * len(value)
    return "•" * (len(value) - VISIBLE_TAIL) + value[-VISIBLE_TAIL:]


def read_state(root: Path | str = Path(".")) -> list[dict]:
    """Состояние ключей для панели: задан ли, маска, за что отвечает."""
    rows = []
    for provider, spec in PROVIDERS.items():
        value = os.environ.get(spec["env"], "")
        rows.append({
            "provider": provider,
            "env": spec["env"],
            "roles": spec["roles"],
            "set": bool(value),
            "mask": mask(value) if value else None,
        })
    return rows


def write_key(root: Path | str, provider: str, value: str) -> dict:
    """Записать ключ в `.env` и в окружение процесса.

    Возвращает строку состояния этого провайдера — ту же, что отдаёт
    `read_state`, чтобы панель обновилась без второго запроса.
    """
    if provider not in PROVIDERS:
        raise KeyError(f"неизвестный провайдер: {provider!r}")

    value = value.strip()
    if not value:
        raise ValueError("пустое значение ключа")
    if "\n" in value or "\r" in value:
        raise ValueError("в значении ключа не может быть перевода строки")

    name = PROVIDERS[provider]["env"]
    path = Path(root) / FILENAME

    lines = []
    if path.is_file():
        # utf-8-sig — та же причина, что в factory/env.py: Блокнот пишет BOM.
        lines = path.read_text(encoding="utf-8-sig").splitlines()

    replaced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        if stripped.split("=", 1)[0].strip() == name:
            lines[i] = f"{name}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{name}={value}")

    body = "\n".join(lines).rstrip("\n") + "\n"

    # Пишем через временный файл: оборванная запись не должна оставить .env
    # наполовину переписанным — тогда потерялись бы и остальные ключи.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    if os.name != "nt":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)

    # Ключ должен работать сразу: человек нажал «Сохранить» и ждёт, что съёмка
    # пойдёт, а не что панель попросит её перезапустить.
    os.environ[name] = value

    return {
        "provider": provider,
        "env": name,
        "roles": PROVIDERS[provider]["roles"],
        "set": True,
        "mask": mask(value),
    }
