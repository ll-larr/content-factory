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


def split_frontmatter(text: str, path) -> tuple[dict, str]:
    """Разобрать документ на YAML-frontmatter и тело.

    Разделитель ищется ПОСТРОЧНО, а не подстрокой: значение внутри frontmatter,
    содержащее '---' (логлайн с прочерком, комментарий-разделитель в шаблоне
    карточки), иначе разрезает документ не там — meta молча обрезается, телом
    становится склейка. Исключения при этом нет.
    """
    # split("\n"), а не splitlines(): последний достаточно щедр (делит и по \x0b,
    # \x1c,  ), а тело артефакта — произвольный текст. Переводы строк к этому
    # моменту уже нормализованы: и Path.read_text, и вывод git из subprocess в
    # текстовом режиме отдают '\n'.
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
    return meta, "\n".join(lines[closing + 1:]).strip()


def load_artifact(path: Path) -> Artifact:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text, path)
    return Artifact(path=path, meta=meta, body=body)


def save_artifact(art: Artifact) -> None:
    front = yaml.safe_dump(art.meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    art.path.parent.mkdir(parents=True, exist_ok=True)
    art.path.write_text(f"{_SEP}\n{front}\n{_SEP}\n\n{art.body.strip()}\n",
                        encoding="utf-8")


def _canonical_re(name: str) -> re.Pattern:
    # Имя экранируется, хотя сейчас зовётся только литералами style/appearance:
    # неэкранированная подстановка в регулярку — разряженное ружьё, имя со
    # спецсимволом совпало бы не с тем блоком (или не скомпилировалось бы).
    escaped = re.escape(name)
    return re.compile(
        rf"<!--\s*canonical:{escaped}\s*-->(.*?)<!--\s*/canonical:{escaped}\s*-->",
        re.DOTALL)


def canonical_block(path: Path, name: str) -> str:
    """Текст между маркерами <!-- canonical:<name> --> и закрывающим.

    Живёт здесь, а не в factory.prompts, чтобы разорвать цикл импортов: гейтам
    (factory.preprod) нужен has_canonical, а factory.prompts нужны artifact_state
    и is_safe_name из тех же гейтов — модули импортировали друг друга, и один из
    двух был вынужден делать это внутри функций. Разбор канонического блока — это
    чтение ТЕЛА артефакта, то есть предмет этого модуля; про плейсхолдеры он не
    знает ничего. factory.prompts заворачивает ArtifactError в PromptError, как
    models.load_card заворачивает его в ModelError.
    """
    path = Path(path)
    if not path.exists():
        raise ArtifactError(f"{path}: файл не найден")
    match = _canonical_re(name).search(load_artifact(path).body)
    if not match:
        raise ArtifactError(f"{path}: нет блока canonical:{name}")
    return match.group(1).strip()


def has_canonical(path: Path, name: str) -> bool:
    """Есть ли в артефакте блок canonical:<name>. Без исключения — нужен гейтам,
    которые обязаны вернуть список проблем, а не упасть."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        return _canonical_re(name).search(load_artifact(path).body) is not None
    except (ArtifactError, OSError):
        # Только непригодность файла. Голый `except Exception` прятал и ошибки
        # программиста: гейт молча отвечал «блока нет» вместо того, чтобы упасть
        # и показать причину.
        return False
