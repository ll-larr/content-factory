"""Кастинг голосов: каталог пресетов, пробы и их отдача в панель.

Имена пресетов о тембре не говорят ничего, а описание сужает выбор, но не решает
его: `Vindemiatrix` подходил Устинье по всем словам и на слух по-русски оказался
негодным (2026-09-05). Поэтому проверяется не «есть список», а «есть что
послушать и по чему сгруппировать».
"""
from pathlib import Path

import pytest

from factory import voices, webapp

REPO = Path(__file__).resolve().parents[1]
KNOWLEDGE = REPO / "knowledge"
MODEL = "gemini_2_5_pro_tts"


# --- каталог ---------------------------------------------------------------

def test_catalog_covers_every_preset_the_model_declares():
    """Карточка голосов и карточка модели расходятся — голос терять нельзя."""
    declared = set(voices.declared_presets(KNOWLEDGE, MODEL))
    listed = {row["preset"] for row in voices.load_voices(KNOWLEDGE, MODEL)}

    assert declared, "в карточке модели не нашёлся список голосов"
    assert declared <= listed, sorted(declared - listed)


def test_voices_are_split_by_gender():
    rows = voices.load_voices(KNOWLEDGE, MODEL)
    genders = {row["gender"] for row in rows}

    assert {"male", "female"} <= genders
    assert all(row["gender"] in ("male", "female", "unknown") for row in rows)


def test_voice_without_a_description_is_shown_not_hidden():
    """У `Algieba` описания нет в исходной карте. Выдумать его нельзя, но и
    делать вид, что пресета не существует, тоже: модель его принимает."""
    rows = {row["preset"]: row for row in voices.load_voices(KNOWLEDGE, MODEL)}

    assert "Algieba" in rows
    assert rows["Algieba"]["gender"] == "unknown"


def test_description_stops_at_the_next_section():
    """Разделы «## Пробелы» и «## Выбрано» — не описание последнего голоса."""
    rows = {row["preset"]: row for row in voices.load_voices(KNOWLEDGE, MODEL)}

    last = rows["Zubenelgenubi"]["description"]
    assert last
    assert "Пробелы" not in last and "Выбрано" not in last


def test_every_described_voice_has_a_register_and_a_summary():
    for row in voices.load_voices(KNOWLEDGE, MODEL):
        if row["gender"] == "unknown":
            continue
        assert row["register"], row["preset"]
        assert row["short"], row["preset"]
        assert row["description"], row["preset"]


def test_sample_phrase_carries_no_voice_name_and_no_markup():
    """В пробе звучит только фраза: имя голоса вслух не нужно, а разметку
    модель читает как слова (живая проба 2026-09-04)."""
    for language, phrase in voices.SAMPLE_TEXT.items():
        assert phrase.strip(), language
        assert "<" not in phrase and "[" not in phrase and "*" not in phrase
        for row in voices.load_voices(KNOWLEDGE, MODEL):
            assert row["preset"].lower() not in phrase.lower()


def test_unknown_model_is_a_refusal_not_an_empty_list():
    with pytest.raises(voices.VoicesError):
        voices.load_voices(KNOWLEDGE, "нет-такой-модели")


def test_card_under_a_wrong_name_is_refused(tmp_path):
    """Карточка объявляет свою модель: файл под чужим именем — рассинхрон."""
    directory = tmp_path / "audio" / "voices"
    directory.mkdir(parents=True)
    (directory / "чужая.md").write_text(
        "---\nid: x\ntype: voices\nstatus: reference\nmodel: своя\n---\n\n"
        "| Kore | жен | высокий | текст |\n", encoding="utf-8")

    with pytest.raises(voices.VoicesError):
        voices.load_voices(tmp_path, "чужая")


# --- пробы -----------------------------------------------------------------

def test_samples_live_next_to_the_card_not_in_a_project():
    """Проба одинакова для всех проектов: держать её в проекте значит платить
    за неё заново на каждом новом."""
    path = voices.sample_path(KNOWLEDGE, MODEL, "ru", "Kore")
    root = KNOWLEDGE / "audio" / "voices" / "samples" / MODEL / "ru"

    assert path.parent.parent == root
    assert path.suffix == ".mp3"


def test_phrase_fingerprint_keeps_recordings_of_different_texts_apart():
    """Фраза уже менялась однажды: в одном каталоге такие пробы сравнивать
    нельзя, а на слух подмену не отличить от особенности голоса."""
    before = voices.phrase_id("ru")
    original = voices.SAMPLE_TEXT["ru"]
    try:
        voices.SAMPLE_TEXT["ru"] = "другая фраза"
        assert voices.phrase_id("ru") != before
        moved = voices.sample_path(KNOWLEDGE, MODEL, "ru", "Kore").parent
        assert moved.name != before
    finally:
        voices.SAMPLE_TEXT["ru"] = original
    assert voices.phrase_id("ru") == before


def test_recorded_phrase_written_next_to_samples(tmp_path):
    voices.write_phrase(tmp_path, MODEL, "ru")

    assert (voices.recorded_phrase(tmp_path, MODEL, "ru")
            == voices.SAMPLE_TEXT["ru"])


def test_catalog_marks_which_samples_exist():
    rows = {row["preset"]: row for row in
            voices.catalog(KNOWLEDGE, MODEL, "ru")}
    for preset, row in rows.items():
        expected = voices.sample_path(KNOWLEDGE, MODEL, "ru", preset).is_file()
        assert row["sample"] is expected, preset


def test_missing_samples_skips_what_is_already_paid_for(tmp_path):
    directory = voices.samples_dir(KNOWLEDGE, MODEL, "ru")
    on_disk = {p.stem for p in directory.glob("*.mp3")} if directory.is_dir() else set()

    missing = set(voices.missing_samples(KNOWLEDGE, MODEL, "ru"))

    assert not (missing & on_disk)


# --- панель ----------------------------------------------------------------

def test_panel_returns_a_tree_of_models_and_genders():
    """Моделей может стать несколько: ответ — список, а не одна модель."""
    data = webapp.voice_catalog("ru", KNOWLEDGE)

    model = next(m for m in data["models"] if m["id"] == MODEL)
    assert model["label"] == "Gemini 2.5 Pro TTS"
    labels = [g["label"] for g in model["groups"]]
    assert "Женские" in labels and "Мужские" in labels
    assert data["phrase"] == voices.SAMPLE_TEXT["ru"]
    assert model["total"] == sum(len(g["voices"]) for g in model["groups"])


def test_panel_shows_markers_instead_of_descriptions():
    """В списке ориентируются по маркерам; описание в ответ не кладётся."""
    data = webapp.voice_catalog("ru", KNOWLEDGE)
    model = next(m for m in data["models"] if m["id"] == MODEL)

    voice = next(v for g in model["groups"] for v in g["voices"]
                 if v["preset"] == "Charon")
    assert voice["markers"] == ["плавный", "низкий", "подкаст"]
    assert "description" not in voice and "short" not in voice


def test_panel_gives_a_url_only_for_a_sample_that_exists():
    data = webapp.voice_catalog("ru", KNOWLEDGE)

    for model in data["models"]:
        for group in model["groups"]:
            for voice in group["voices"]:
                assert bool(voice["sample_url"]) is bool(voice["sample"]), voice


def test_panel_refuses_an_unknown_sample_language():
    with pytest.raises(webapp.WebappError):
        webapp.voice_catalog("эльфийский", KNOWLEDGE)


def test_sample_file_refuses_a_path_that_escapes_knowledge():
    with pytest.raises(webapp.WebappError):
        webapp.voice_sample_file(MODEL, "ru", "../../../CLAUDE", KNOWLEDGE)


def test_sample_file_refuses_what_was_never_recorded():
    with pytest.raises(webapp.WebappError):
        webapp.voice_sample_file(MODEL, "ru", "НетТакогоПресета", KNOWLEDGE)


class FakeRunner:
    def __init__(self):
        self.cmd = None

    def start(self, cmd, meta):
        self.cmd = cmd
        return {"cmd": cmd, "meta": meta}


def test_generation_runs_the_same_cli_a_human_runs():
    runner = FakeRunner()

    webapp.run_voice_samples(runner, "ru", MODEL, ["Kore"])

    assert runner.cmd[1].endswith("voice_samples.py")
    assert "--voice" in runner.cmd and "Kore" in runner.cmd
    # Без --yes подпроцесс спросил бы подтверждение у стдина, которого нет.
    assert "--yes" in runner.cmd


def test_generation_refuses_a_preset_name_that_is_not_a_file_name():
    """Имя приходит из браузера и становится аргументом команды."""
    with pytest.raises(webapp.WebappError):
        webapp.run_voice_samples(FakeRunner(), "ru", MODEL, ["../rm"])


def test_generation_refuses_an_unknown_language():
    with pytest.raises(webapp.WebappError):
        webapp.run_voice_samples(FakeRunner(), "клингонский", MODEL, None)


# --- балансы ---------------------------------------------------------------

def test_search_provider_shows_a_reason_not_a_traceback(monkeypatch):
    """Tavily не генерирует медиа: `get_provider` на нём падает, и показывать
    человеку «unknown provider» вместо причины прочерка — врать о причине."""
    rows = {row["provider"]: row for row in webapp.balances(KNOWLEDGE)}

    assert rows["Tavily"]["balance"] is None
    assert "unknown provider" not in rows["Tavily"]["reason"]
    assert "кредит" in rows["Tavily"]["reason"]
