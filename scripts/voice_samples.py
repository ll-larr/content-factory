"""Пробы голосов: по одной короткой реплике на каждый пресет модели речи.

Запускать из корня репозитория:
  python scripts/voice_samples.py --model gemini_2_5_pro_tts --language ru
  python scripts/voice_samples.py --voice Erinome --yes

Зачем: имена пресетов о тембре не говорят ничего, а описание сужает выбор, но не
решает его — `Vindemiatrix` подходил Устинье по всем словам и на слух по-русски
оказался негодным (2026-09-05). Выбор голоса делается ушами, значит панель
обязана дать послушать, значит пробы должны существовать файлами.

Проба принадлежит МОДЕЛИ, а не проекту: она одинакова для всех проектов и
снимается один раз. Уже снятое не переснимаем — за него заплачено, а звучит оно
так же.

У модели нет ни каталога готовых сэмплов, ни публичных ссылок на них: превью
голосов Gemini живёт только внутри Google AI Studio (проверено 2026-09-07).
Поэтому пробы генерируются, и это стоит денег — смета показывается ДО траты.

Коды выхода: 0 успех; 1 ошибка данных или генерации; 2 гейт (нет ключа, карточка
запрещает трату); 3 человек отказался от траты.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory import voices                                     # noqa: E402
from factory.env import load_env                               # noqa: E402
from factory.models import (ModelError, find_card,             # noqa: E402
                            validate_audio_model)
from factory.providers import ProviderError, get_provider      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = Path("knowledge")
DEFAULT_MODEL = "gemini_2_5_pro_tts"
DEFAULT_PROVIDER = "wavespeed"


def _language_value(card: dict, language: str) -> str | None:
    """Код языка в том виде, в каком его хочет ЭТА модель.

    Соответствие живёт в карточке (`language_map`), а не в коде: у gemini это
    «Russian (Russia)», у qwen3 — «Russian». Тот же источник, что знает имена
    полей запроса.
    """
    return (card.get("language_map") or {}).get(language)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    ap.add_argument("--language", default="ru")
    ap.add_argument("--voice", action="append",
                    help="снять пробу только этих пресетов (можно несколько раз)")
    ap.add_argument("--limit", type=int,
                    help="снять не больше стольких проб за запуск")
    ap.add_argument("--yes", action="store_true", help="не спрашивать про трату")
    args = ap.parse_args(argv)

    load_env(ROOT)

    text = voices.SAMPLE_TEXT.get(args.language)
    if not text:
        print(f"нет фразы пробы для языка {args.language!r}; "
              f"известны {sorted(voices.SAMPLE_TEXT)}")
        return 1

    try:
        card = find_card(KNOWLEDGE_DIR, args.model)
    except (ModelError, OSError) as e:
        print(f"карточка модели не читается: {e}")
        return 1

    language_value = _language_value(card, args.language)
    if language_value is None:
        print(f"{args.model}: в карточке нет language_map[{args.language!r}] — "
              "без него поле language не уедет провайдеру вовсе")
        return 1

    # Гейт трат карточного уровня — тот же, что у платных стадий: `skeleton`
    # генерировать нельзя. Своей копии проверки здесь нет.
    problems = validate_audio_model(card, args.provider, "tts")
    if problems:
        for p in problems:
            print(f"  - {p}")
        return 2

    try:
        catalog = voices.catalog(KNOWLEDGE_DIR, args.model, args.language)
    except voices.VoicesError as e:
        print(f"каталог голосов не прочитать: {e}")
        return 1

    wanted = set(args.voice or [])
    known = {row["preset"] for row in catalog}
    unknown = sorted(wanted - known)
    if unknown:
        print(f"нет таких пресетов: {unknown}; известны {sorted(known)}")
        return 1

    todo = [row["preset"] for row in catalog
            if not row["sample"] and (not wanted or row["preset"] in wanted)]
    if args.limit is not None:
        todo = todo[:max(0, args.limit)]

    if not todo:
        print(f"пробы всех голосов уже сняты ({args.model}, {args.language})")
        return 0

    provider = get_provider(args.provider, KNOWLEDGE_DIR)
    params = {"text": text, "language": language_value, "voice": todo[0]}
    problems = provider.preflight_problems(args.model, params)
    if problems:
        for p in problems:
            print(f"  - {p}")
        return 2

    try:
        per_call = provider.estimate(args.model, params)
    except (ModelError, ProviderError) as e:
        print(f"смету не посчитать: {e}")
        return 1
    total = per_call * len(todo)

    print(f"модель: {args.model} · провайдер: {args.provider} · "
          f"язык: {args.language}")
    print(f"фраза: {text}")
    print(f"снять проб: {len(todo)} по ${per_call:.4f} = ${total:.4f}")
    if provider.supports_balance:
        try:
            balance = provider.balance()
            print(f"на счету: ${balance:.4f}"
                  + ("" if balance >= total
                     else " -- НЕ ХВАТИТ, генерация оборвётся на середине"))
        except ProviderError as e:
            print(f"баланс неизвестен: {e}")

    if not args.yes:
        try:
            answer = input("Тратить? [y/N] ").strip().lower()
        except EOFError:
            # Запуск без терминала (панель, скрипт, CI). Молчание — не согласие
            # тратить: подтверждение обязано быть явным, и для этого есть --yes.
            print("подтвердить трату некому: запусти с --yes или из терминала")
            return 3
        if answer not in ("y", "yes", "д", "да"):
            print("отменено")
            return 3

    dest_dir = voices.samples_dir(KNOWLEDGE_DIR, args.model, args.language)
    voices.write_phrase(KNOWLEDGE_DIR, args.model, args.language)

    failed: list[str] = []
    for i, preset in enumerate(todo, 1):
        dest = voices.sample_path(KNOWLEDGE_DIR, args.model, args.language, preset)
        print(f"[{i}/{len(todo)}] {preset} ...", flush=True)
        try:
            job = provider.submit(args.model, {
                "text": text, "language": language_value, "voice": preset})
            provider.wait(job)
            provider.download(job, dest)
        except (ProviderError, OSError) as e:
            # Один голос не сорвал остальные: за уже снятые заплачено, и бросать
            # их из-за отказа по одному пресету незачем.
            print(f"    не вышло: {e}")
            failed.append(preset)
            continue
        print(f"    записан {dest}")

    if failed:
        print(f"не сняты: {failed}")
        return 1
    print(f"готово: {len(todo)} проб в {dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
