"""Манифест проекта — память завода (спека §10).

Статусы: pending -> generating -> done | rejected | accepted_with_notes.
rejected/accepted_with_notes -> pending = перегенерация.
generating -> pending = возврат в очередь после технического сбоя.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

STATUSES = {"pending", "generating", "done", "rejected", "accepted_with_notes"}
KNOWN_FIELDS = {"file", "job_id", "credits_spent", "reject_reason", "notes", "attempts"}
ALLOWED = {
    "pending": {"generating"},
    "generating": {"done", "rejected", "accepted_with_notes", "pending"},
    "rejected": {"pending"},
    "accepted_with_notes": {"pending"},
    "done": set(),
}


class ManifestError(ValueError):
    pass


class Manifest:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"items": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, item_id: str, kind: str) -> None:
        self.data["items"].setdefault(item_id, {
            "kind": kind, "status": "pending", "attempts": 0,
            "credits_spent": 0.0, "file": None, "job_id": None,
            "reject_reason": None, "notes": None,
        })

    def get(self, item_id: str) -> dict:
        try:
            return self.data["items"][item_id]
        except KeyError:
            raise ManifestError(f"unknown item_id: {item_id!r}") from None

    def set_status(self, item_id: str, status: str, **fields) -> None:
        if status not in STATUSES:
            raise ManifestError(f"unknown status: {status!r}")
        unknown = set(fields) - KNOWN_FIELDS
        if unknown:
            raise ManifestError(f"unknown fields: {sorted(unknown)}")
        item = self.get(item_id)
        if status not in ALLOWED[item["status"]]:
            raise ManifestError(
                f"{item_id}: {item['status']} -> {status} is not allowed")
        if status == "rejected" and not fields.get("reject_reason"):
            raise ManifestError(f"{item_id}: rejected requires reject_reason")
        item.update(status=status, **fields)

    def pending(self, kind: str | None = None) -> list[str]:
        return [i for i, it in self.data["items"].items()
                if it["status"] == "pending"
                and (kind is None or it["kind"] == kind)]

    def credits_total(self) -> float:
        return sum(it["credits_spent"] for it in self.data["items"].values())
