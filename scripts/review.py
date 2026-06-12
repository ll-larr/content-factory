"""CLI ревью сгенерированных кадров и отрезков (спека ревью §5).

Для ревьюера — человека и Claude-режиссёра. Запускать из корня репозитория:
  python scripts/review.py --project projects/pilot list --status generated
  python scripts/review.py --project projects/pilot accept <id> [<id> ...]
  python scripts/review.py --project projects/pilot accept-notes <id> --notes "..."
  python scripts/review.py --project projects/pilot reject <id> --reason "..."
  python scripts/review.py --project projects/pilot requeue <id>

requeue — решение человека после лимита отклонений: возвращает rejected или
accepted_with_notes в pending; reject_count при этом НЕ сбрасывается (журнал).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory.manifest import Manifest, ManifestError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True)
    sub = ap.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="показать items манифеста")
    p_list.add_argument("--status", help="фильтр по статусу")

    p_accept = sub.add_parser("accept", help="generated -> done")
    p_accept.add_argument("ids", nargs="+")

    p_notes = sub.add_parser("accept-notes",
                             help="generated -> accepted_with_notes")
    p_notes.add_argument("id", help="один item id")
    p_notes.add_argument("--notes", required=True)

    p_reject = sub.add_parser("reject", help="generated -> rejected")
    p_reject.add_argument("id", help="один item id")
    p_reject.add_argument("--reason", required=True)

    p_requeue = sub.add_parser(
        "requeue", help="rejected | accepted_with_notes -> pending")
    p_requeue.add_argument("id", help="один item id")

    args = ap.parse_args(argv)
    manifest = Manifest(Path(args.project) / "manifest.json")

    if args.command == "list":
        for item_id in sorted(manifest.data["items"]):
            it = manifest.data["items"][item_id]
            if args.status and it["status"] != args.status:
                continue
            print(f"{item_id}\t{it['status']}\t"
                  f"attempts={it.get('attempts', 0)}\t"
                  f"rejects={it.get('reject_count', 0)}\t{it.get('file') or '-'}")
        return 0

    # Мутации — всё или ничего: при ошибке манифест не сохраняется
    try:
        if args.command == "accept":
            for item_id in args.ids:
                manifest.set_status(item_id, "done")
        elif args.command == "accept-notes":
            manifest.set_status(args.id, "accepted_with_notes",
                                notes=args.notes)
        elif args.command == "reject":
            manifest.set_status(args.id, "rejected",
                                reject_reason=args.reason)
        elif args.command == "requeue":
            manifest.set_status(args.id, "pending")
    except ManifestError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        if args.command == "accept" and len(args.ids) > 1:
            print("Ни один из переходов не сохранён.", file=sys.stderr)
        return 1
    manifest.save()
    return 0


if __name__ == "__main__":
    # Защита от кириллицы на legacy cp1251-консоли Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
