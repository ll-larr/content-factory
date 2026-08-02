"""Текстовый артефакт пре-продакшна: YAML-frontmatter + значимое тело.

Спека 2026-08-02 §4. От карточки модели (factory.models) отличается тем, что тело
здесь значимо: по нему считается content_sha, и правка тела после одобрения обязана
быть заметна гейту.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

_SEP = "---"


class ArtifactError(ValueError):
    pass


def body_sha(body: str) -> str:
    """sha256 тела. Нормализуем переводы строк и краевые пробелы: иначе один и тот же
    текст, сохранённый на Windows и в git, давал бы разные хеши и артефакт «устаревал»
    бы сам собой."""
    normalized = body.replace("\r\n", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class Artifact:
    path: Path
    meta: dict
    body: str

    @property
    def sha(self) -> str:
        return body_sha(self.body)


def load_artifact(path: Path) -> Artifact:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_SEP):
        raise ArtifactError(f"{path}: нет YAML-frontmatter")
    parts = text.split(_SEP, 2)
    if len(parts) < 3:
        raise ArtifactError(f"{path}: frontmatter не закрыт '{_SEP}'")
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise ArtifactError(f"{path}: некорректный YAML — {e}") from None
    if not isinstance(meta, dict):
        raise ArtifactError(f"{path}: frontmatter не является YAML-словарём")
    return Artifact(path=path, meta=meta, body=parts[2].strip())


def save_artifact(art: Artifact) -> None:
    front = yaml.safe_dump(art.meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    art.path.parent.mkdir(parents=True, exist_ok=True)
    art.path.write_text(f"{_SEP}\n{front}\n{_SEP}\n\n{art.body.strip()}\n",
                        encoding="utf-8")
