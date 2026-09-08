"""Каталог голосов модели речи и пробы к нему.

Имена пресетов о тембре не говорят НИЧЕГО, а описание сужает выбор, но не решает
его: `Vindemiatrix` подходил Устинье по всем словам и на слух по-русски оказался
негодным (2026-09-05). Поэтому выбор голоса — всегда прослушивание, и панель
обязана дать его послушать, а не предложить список имён.

Источник данных — карточка голосов `knowledge/audio/voices/<модель>.md`, ровно
как у карточек моделей: frontmatter машине, проза человеку. Второго списка
голосов не заводить — у каждой модели речи свой набор, и общий список предлагал
бы голос, которого у выбранной модели нет.

Пробы лежат рядом с карточкой
(`voices/samples/<модель>/<язык>/<отпечаток фразы>/<пресет>.mp3`) и принадлежат
МОДЕЛИ, а не проекту: они одинаковы для всех проектов, и держать их в проекте
значило бы платить за них заново на каждом новом.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from factory.artifact import ArtifactError, split_frontmatter

VOICES_DIRNAME = "voices"
SAMPLES_DIRNAME = "samples"

# Пол в карточке записан по-русски и остаётся таким на экране. Машинное значение
# нужно для группировки: панель показывает мужские и женские отдельно.
GENDERS = {"муж": "male", "жен": "female"}
GENDER_LABELS = {"male": "Мужские", "female": "Женские", "unknown": "Пол не определён"}

# Фраза пробы. Короткая, без имени голоса (его слышно не нужно) и без разметки:
# теги вида <sigh> модель читает вслух. Одна и та же для всех пресетов —
# сравнивать голоса можно только на одинаковом тексте.
SAMPLE_TEXT = {
    "ru": "Мой голос звучит так и никак иначе. Не забудь его!",
    "en": "This is exactly how my voice sounds, and no other way. Remember it!",
}

# Рядом с пробами лежит текст, которым они сняты, — чтобы человек, открывший
# каталог, видел, что именно там наговорено.
PHRASE_FILE = "phrase.txt"

_ROW = re.compile(
    r"^\|\s*(?P<preset>[A-Za-z][\w-]*)\s*\|\s*(?P<gender>[^|]*?)\s*\|"
    r"\s*(?P<register>[^|]*?)\s*\|\s*(?P<markers>[^|]*?)\s*\|"
    r"\s*(?P<short>[^|]*?)\s*\|\s*$",
    re.MULTILINE)
_SECTION = re.compile(r"^###\s+(?P<preset>[A-Za-z][\w-]*)\s*$", re.MULTILINE)


class VoicesError(ValueError):
    """Каталог голосов не прочитать."""


def card_path(knowledge_dir: Path | str, model: str) -> Path:
    return Path(knowledge_dir) / "audio" / VOICES_DIRNAME / f"{model}.md"


def phrase_id(language: str) -> str:
    """Короткий отпечаток фразы пробы — сегмент пути к пробам этого текста.

    Фраза уже менялась однажды (2026-09-07). Без отпечатка в пути пробы,
    снятые разными текстами, легли бы в один каталог: сравнивать тембры по
    разным фразам нельзя, а на слух подмену не отличить от особенности голоса.
    Отпечаток в пути делает смешение невозможным, ничего не удаляя, — старые
    пробы просто остаются в своём каталоге.
    """
    phrase = SAMPLE_TEXT.get(language, "")
    return hashlib.sha256(phrase.encode("utf-8")).hexdigest()[:8]


def samples_dir(knowledge_dir: Path | str, model: str, language: str) -> Path:
    return (Path(knowledge_dir) / "audio" / VOICES_DIRNAME / SAMPLES_DIRNAME
            / model / language / phrase_id(language))


def sample_path(knowledge_dir: Path | str, model: str, language: str,
                preset: str) -> Path:
    return samples_dir(knowledge_dir, model, language) / f"{preset}.mp3"


def _full_descriptions(body: str) -> dict[str, str]:
    """Текст под каждым `### Пресет` до следующего заголовка."""
    found: dict[str, str] = {}
    matches = list(_SECTION.finditer(body))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        chunk = body[start:end]
        # Секция описаний кончается следующим разделом второго уровня
        # («## Пробелы», «## Выбрано на русском»), и его текст в описание голоса
        # попасть не должен.
        chunk = re.split(r"^##\s", chunk, maxsplit=1, flags=re.MULTILINE)[0]
        found[match.group("preset")] = chunk.strip()
    return found


def load_voices(knowledge_dir: Path | str, model: str) -> list[dict]:
    """Голоса модели: пресет, пол, регистр, короткое и полное описание.

    Пресет без строки в таблице — не ошибка чтения, а честный пробел: у
    `Algieba` описания нет в исходной карте, и выдумать его нельзя. Такой голос
    отдаётся с полом `unknown`, и панель показывает его отдельно — вслепую
    выбирать нечего, но и прятать существующий пресет незачем.
    """
    path = card_path(knowledge_dir, model)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise VoicesError(f"нет карточки голосов {path}: {e}") from None
    try:
        meta, body = split_frontmatter(text, path)
    except ArtifactError as e:
        raise VoicesError(f"{path}: {e}") from None
    if meta.get("model") != model:
        raise VoicesError(
            f"{path}: карточка объявляет model={meta.get('model')!r}, "
            f"а лежит под именем {model!r}")

    full = _full_descriptions(body)
    rows: dict[str, dict] = {}
    for match in _ROW.finditer(body):
        preset = match.group("preset")
        gender = GENDERS.get(match.group("gender").strip(), "unknown")
        register = match.group("register").strip()
        # Тональность — такой же маркер, как тон и применение, и в панели
        # показывается в одном ряду с ними. Отдельным полем она остаётся для
        # тех, кому нужен именно регистр (сортировка, будущий фильтр).
        markers = [m.strip() for m in match.group("markers").split(",") if m.strip()]
        rows[preset] = {
            "preset": preset,
            "gender": gender,
            "gender_label": match.group("gender").strip() or "?",
            "register": register,
            "markers": ([markers[0]] if markers else []) + (
                [register] if register else []) + markers[1:],
            "short": match.group("short").strip(),
            "description": full.get(preset, ""),
        }

    for preset in declared_presets(knowledge_dir, model):
        rows.setdefault(preset, {
            "preset": preset, "gender": "unknown", "gender_label": "?",
            "register": "", "markers": [], "short": "", "description": ""})

    if not rows:
        raise VoicesError(f"{path}: в карточке нет ни одного голоса")
    return [rows[name] for name in sorted(rows)]


def declared_presets(knowledge_dir: Path | str, model: str) -> list[str]:
    """Пресеты, объявленные КАРТОЧКОЙ МОДЕЛИ, а не карточкой голосов.

    Два списка расходятся: у `Algieba` пресет есть, а описания нет. Правда о
    том, какие голоса модель принимает, — у модели; описания вторичны, и
    потерять из-за их отсутствия целый голос нельзя.

    Читаем ТЕЛО карточки: `models.load_card` его отбрасывает — ему важна только
    матрица возможностей, а список голосов живёт в прозе.
    """
    for path in sorted(Path(knowledge_dir).rglob(f"{model}.md")):
        if path.parent.name == VOICES_DIRNAME:
            continue                       # это карточка голосов, а не модели
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^##\s*Голоса\s*$\n+(?P<list>.+?)(?:\n\n|\Z)",
                          body, re.DOTALL | re.MULTILINE)
        if match:
            return sorted(set(re.findall(r"\b[A-Z][A-Za-z]{2,}\b",
                                         match.group("list"))))
    return []


def available_models(knowledge_dir: Path | str) -> list[str]:
    """Модели речи, у которых есть карточка голосов.

    Список — из файлов, а не из литерала в коде: добавить провайдера с его
    голосами значит положить рядом ещё одну карточку, а не править панель.
    """
    directory = Path(knowledge_dir) / "audio" / VOICES_DIRNAME
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.md")
                  if not p.name.startswith("_"))


def model_label(knowledge_dir: Path | str, model: str) -> str:
    """Человеческое имя модели для заголовка списка. Живёт в карточке."""
    try:
        meta, _body = split_frontmatter(
            card_path(knowledge_dir, model).read_text(encoding="utf-8"),
            card_path(knowledge_dir, model))
    except (ArtifactError, OSError):
        return model
    return str(meta.get("label") or model)


def recorded_phrase(knowledge_dir: Path | str, model: str,
                    language: str) -> str | None:
    """Фраза, которой сняты лежащие рядом пробы; None — пробы не снимались."""
    path = samples_dir(knowledge_dir, model, language) / PHRASE_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def write_phrase(knowledge_dir: Path | str, model: str, language: str) -> None:
    """Положить рядом с пробами текст, которым они сняты.

    Отпечаток фразы уже стоит в пути, и смешаться пробы не могут; файл нужен
    человеку, открывшему каталог: восьми шестнадцатеричных цифр мало, чтобы
    понять, что там наговорено.
    """
    directory = samples_dir(knowledge_dir, model, language)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / PHRASE_FILE).write_text(
        SAMPLE_TEXT.get(language, "").strip() + "\n", encoding="utf-8")


def catalog(knowledge_dir: Path | str, model: str, language: str) -> list[dict]:
    """Голоса вместе с тем, снята ли по каждому проба на этом языке.

    «Снята» означает «снята ТЕКУЩЕЙ фразой»: каталог проб адресуется её
    отпечатком, поэтому проба другого текста сюда просто не попадает.
    """
    rows = load_voices(knowledge_dir, model)
    for row in rows:
        path = sample_path(knowledge_dir, model, language, row["preset"])
        row["sample"] = path.is_file()
    return rows


def missing_samples(knowledge_dir: Path | str, model: str,
                    language: str) -> list[str]:
    """Пресеты, по которым пробы ещё нет. Уже снятое не переснимаем: за него
    заплачено, а звучит оно одинаково."""
    return [row["preset"] for row in catalog(knowledge_dir, model, language)
            if not row["sample"]]
