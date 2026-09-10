"""Текстовые стадии: промпт из скилла и разбор ответа модели.

Методика не переписывается в код: системным промптом становится тело самого
скилла. Правка скилла обязана менять оба движка сразу.
"""
import json
from pathlib import Path

import pytest

from factory.text import stages

REPO = Path(__file__).resolve().parents[1]

ANSWER = """Готово, вот файлы.

=== FILE: bible/idea.md ===
Смотрительница маяка и жестяная ворона.
=== END FILE ===

=== FILE: bible/style-guide.md ===
Холодный свет, тёплая жесть.
=== END FILE ===
"""


@pytest.fixture
def project(tmp_path):
    pdir = tmp_path / "проект"
    (pdir / "bible").mkdir(parents=True)
    (pdir / "episodes" / "ep01").mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "проект", "type": "series", "genre": "animation",
        "theme": "маяк", "episodes": 1, "episode_duration_sec": 60,
        "language": "ru",
        "models": {"image": {"model": "z_image_turbo"},
                   "video": {"model": "vidu_q2_turbo"}},
    }, ensure_ascii=False), encoding="utf-8")
    (pdir / "bible" / "idea.md").write_text(
        "---\nstatus: draft\n---\nстарая идея\n", encoding="utf-8")
    return pdir


# --- описание стадий -------------------------------------------------------

def test_every_stage_points_at_an_existing_skill():
    for stage in stages.STAGES.values():
        path = REPO / ".claude" / "skills" / stage.skill / "SKILL.md"
        assert path.is_file(), stage.skill


def test_stages_cover_the_text_half():
    assert set(stages.STAGES) >= {"pitch", "story", "script", "characters",
                                  "storyboard", "audio_plan"}


# --- сборка промпта --------------------------------------------------------

def test_prompt_carries_skill_body_not_frontmatter(project):
    built = stages.build_prompt("pitch", project, REPO, request="давай про маяк")

    assert "Питч (три варианта идеи)" in built.system
    assert "name: factory-pitch" not in built.system, "frontmatter скилла машине не нужен"


def test_prompt_carries_genre_card(project):
    built = stages.build_prompt("story", project, REPO, request="")
    assert "Мультфильм" in built.system
    assert "canonical:appearance" in built.system or "каноническая внешность" in built.system


def test_prompt_carries_input_artifacts(project):
    built = stages.build_prompt("story", project, REPO, request="")
    assert "старая идея" in built.user
    assert "маяк" in built.user, "тема проекта — часть задания"


def test_prompt_carries_human_request(project):
    built = stages.build_prompt("story", project, REPO, request="больше про ворону")
    assert "больше про ворону" in built.user


def test_prompt_names_expected_output_files(project):
    """Модель должна знать, какие файлы от неё ждут, иначе ответит прозой."""
    built = stages.build_prompt("story", project, REPO, request="")
    assert "bible/idea.md" in built.user
    assert "=== FILE:" in built.system


def test_unknown_stage_is_rejected(project):
    with pytest.raises(stages.StageError):
        stages.build_prompt("нет-такой", project, REPO, request="")


def test_stage_absent_in_genre_is_rejected(project):
    """У познавательного нет персонажей — стадию нельзя даже собрать."""
    path = project / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["genre"] = "educational"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(stages.StageError) as e:
        stages.build_prompt("characters", project, REPO, request="")
    assert "educational" in str(e.value)


# --- разбор ответа ---------------------------------------------------------

def test_parses_file_blocks():
    files = stages.parse_files(ANSWER)
    assert files["bible/idea.md"].strip().startswith("Смотрительница")
    assert "Холодный свет" in files["bible/style-guide.md"]


def test_answer_without_blocks_is_an_error():
    with pytest.raises(stages.StageError):
        stages.parse_files("просто текст без файлов")


def test_write_files_refuses_paths_outside_stage_outputs(project):
    """Модель пишет только туда, куда стадии положено, — и никуда больше."""
    with pytest.raises(stages.StageError):
        stages.write_files("story", project, {"secrets.txt": "у"})


def test_write_files_refuses_escaping_paths(project):
    with pytest.raises(stages.StageError):
        stages.write_files("story", project, {"../../etc/passwd": "у"})


def test_write_files_saves_declared_outputs(project):
    written = stages.write_files("story", project, stages.parse_files(ANSWER))

    assert (project / "bible" / "idea.md").read_text(encoding="utf-8").count(
        "Смотрительница") == 1
    assert set(written) == {"bible/idea.md", "bible/style-guide.md"}


def test_written_artifact_keeps_draft_frontmatter(project):
    """status ставит только approve — стадия пишет черновик, а не одобренное."""
    stages.write_files("story", project, stages.parse_files(ANSWER))

    body = (project / "bible" / "idea.md").read_text(encoding="utf-8")
    assert "status: draft" in body


def test_pitch_writes_nothing(project):
    """Питч — разговор: пока вариант не выбран, записывать нечего."""
    assert stages.STAGES["pitch"].outputs == ()
    with pytest.raises(stages.StageError):
        stages.write_files("pitch", project, {"bible/idea.md": "x"})


# --- сырой ответ стадии остаётся на диске (2026-09-09) ---------------------

class SavingEngine:
    name = "fake"
    label = "фейковый движок"

    def __init__(self, answer="=== FILE: bible/idea.md ===\nтело\n=== END FILE ==="):
        self.answer = answer

    def complete(self, system, user, *, model=None, effort=None):
        return self.answer


def test_answer_is_saved_next_to_the_project(project):
    """За ответ уже заплачено токенами: он не должен жить только в консоли."""
    answer = stages.ask(SavingEngine(), "система", "задание",
                        project_dir=project, stage_id="story")

    saved = project / stages.LAST_ANSWER
    assert answer in saved.read_text(encoding="utf-8")
    assert "story" in saved.read_text(encoding="utf-8"), "видно, чей это ответ"


def test_episode_answer_is_saved_inside_the_episode(project):
    stages.ask(SavingEngine(), "система", "задание", project_dir=project,
               stage_id="script", episode="ep01")

    assert (project / "episodes" / "ep01" / stages.LAST_ANSWER).is_file()


def test_saving_never_breaks_the_stage(project, monkeypatch):
    """Не записался черновик — стадия всё равно должна отдать ответ."""
    def boom(*a, **k):
        raise OSError("диск только для чтения")

    monkeypatch.setattr(stages.Path, "write_text", boom)

    assert stages.ask(SavingEngine("ответ"), "с", "з", project_dir=project,
                      stage_id="story") == "ответ"
