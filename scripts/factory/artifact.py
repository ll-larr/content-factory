"""Текстовый артефакт пре-продакшна: YAML-frontmatter + значимое тело.

Спека 2026-08-02 §4. От карточки модели (factory.models) отличается тем, что тело
здесь значимо: по нему считается content_sha, и правка тела после одобрения обязана
быть заметна гейту.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_SEP = "---"
# Разделитель ищем построчно (регексом на ЦЕЛУЮ строку), а не подстрокой text.split("---").
# Причина: PyYAML не кавычит скаляр вида "a---b", поэтому значение meta с "---" в
# середине строки (например logline на русском — прочерк там пишут часто) при
# substring-split разрежет документ не там и молча испортит meta/body без исключения.
# Построчный разбор такому значению ничего не сделает — "---" внутри чужой строки не
# совпадает с regex на всю строку.
_SEP_LINE_RE = re.compile(r"-{3}[ \t]*")


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
    lines = text.split("\n")
    if not lines or not _SEP_LINE_RE.fullmatch(lines[0]):
        raise ArtifactError(f"{path}: нет YAML-frontmatter")
    closing = next(
        (i for i in range(1, len(lines)) if _SEP_LINE_RE.fullmatch(lines[i])), None
    )
    if closing is None:
        raise ArtifactError(f"{path}: frontmatter не закрыт '{_SEP}'")
    try:
        meta = yaml.safe_load("\n".join(lines[1:closing])) or {}
    except yaml.YAMLError as e:
        raise ArtifactError(f"{path}: некорректный YAML — {e}") from None
    if not isinstance(meta, dict):
        raise ArtifactError(f"{path}: frontmatter не является YAML-словарём")
    body = "\n".join(lines[closing + 1:])
    return Artifact(path=path, meta=meta, body=body.strip())


def save_artifact(art: Artifact) -> None:
    front = yaml.safe_dump(art.meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    art.path.parent.mkdir(parents=True, exist_ok=True)
    art.path.write_text(f"{_SEP}\n{front}\n{_SEP}\n\n{art.body.strip()}\n",
                        encoding="utf-8")
