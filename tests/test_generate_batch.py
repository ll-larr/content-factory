"""Тесты батч-генератора generate_batch.py (спека §8; мультипровайдерный слой).

Провайдер замокан фейком (gb.get_provider). Стадия audio удалена (вынесена в
отдельную задачу — генерация звука на ElevenLabs).
"""
import json
from pathlib import Path

import pytest

import generate_batch as gb
import review
from factory.artifact import Artifact, body_sha, load_artifact, save_artifact
from factory.ffmpeg_tools import FfmpegError
from factory.manifest import Manifest, ManifestError
from factory.providers.base import BaseHTTPProvider, ProviderError

VIDEO_CARD = (
    "---\nid: seedance_2_0\ntype: video\nstatus: verified\n"
    "providers:\n"
    "  wavespeed:\n"
    "    pricing: scaled\n"
    "    supports_start_end: true\n"
    "    res_mult: {720p: 1.0, 1080p: 1.4}\n"
    "    tiers: { fast: { id: \"wsp/seedance-fast\", usd_per_sec: 0.10 } }\n"
    "    default_tier: fast\n"
    "---\n# Seedance 2.0\n")

IMAGE_CARD = (
    "---\nid: z_image\ntype: image\nstatus: verified\n"
    "providers:\n"
    "  wavespeed:\n"
    "    id: \"wsp/z-image\"\n"
    "    pricing: flat\n"
    "    usd_per_image: 0.005\n"
    "---\n# Z Image\n")


def write_image_card(tmp_path):
    """Карточка image-модели z_image (verified, wavespeed) для гейта раскадровки."""
    idir = tmp_path / "knowledge" / "images"
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "z_image.md").write_text(IMAGE_CARD, encoding="utf-8")


def write_script(project_dir, episode="ep01", characters=()):
    """Одобренный сценарий эпизода: гейт storyboard (спека 2026-08-02 §5) требует
    его наравне со стайл-гайдом, иначе раскадровка стартовала бы на неодобренном
    тексте."""
    body = "сценарий"
    meta = {"kind": "script", "status": "approved", "content_sha": body_sha(body)}
    if characters:
        meta["characters"] = list(characters)
    save_artifact(Artifact(path=project_dir / "episodes" / episode / "script.md",
                           meta=meta, body=body))


def write_style_guide(project_dir):
    """Style-guide проекта с каноническим блоком: без него {{style}} в промптах
    кадров не проходит ни гейт §10, ни expand_prompt. content_sha обязателен —
    иначе artifact_state справедливо считает артефакт изменённым после одобрения."""
    body = "<!-- canonical:style -->flat 2D cartoon<!-- /canonical:style -->"
    save_artifact(Artifact(
        path=project_dir / "bible" / "style-guide.md",
        meta={"kind": "style-guide", "status": "approved",
              "content_sha": body_sha(body)},
        body=body))


def write_character(project_dir, name):
    """Одобренная карточка персонажа с каноническим блоком внешности."""
    body = f"<!-- canonical:appearance -->orange cat {name}<!-- /canonical:appearance -->"
    save_artifact(Artifact(
        path=project_dir / "bible" / "characters" / f"{name}.md",
        meta={"kind": "character", "status": "approved",
              "content_sha": body_sha(body)},
        body=body))


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """Мини-проект: 3 кадра, 2 отрезка; CWD = tmp_path (как корень репо).

    Провайдеры заданы явно (wavespeed), карточка видео содержит блок providers.
    """
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "resolution": "720p",
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed",
                             "tier": "fast"}},
    }), encoding="utf-8")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "{{style}} a"}, {"n": 2, "prompt": "{{style}} b"},
                   {"n": 3, "prompt": "{{style}} c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    kdir = tmp_path / "knowledge" / "video"
    kdir.mkdir(parents=True)
    (kdir / "seedance_2_0.md").write_text(VIDEO_CARD, encoding="utf-8")
    write_image_card(tmp_path)
    write_style_guide(pdir)
    write_script(pdir)
    monkeypatch.chdir(tmp_path)
    return pdir


class FakeProvider(BaseHTTPProvider):
    """Замена реального провайдера: фиксирует submit-параметры, пишет файлы.

    Наследуется от BaseHTTPProvider ради НАСТОЯЩЕГО preflight_problems: проверка
    наличия ключа живёт в слое провайдера (изоляция провайдера — правило репо), и
    подменять её фейком значило бы тестировать мок. `api_key_env` пуст — ключ
    фейку не нужен, и это ровно то поведение, которое обязано сохраниться
    (D-2: пустое api_key_env = «ключ не нужен»).
    """
    name = "fake"

    def __init__(self):
        super().__init__(knowledge_dir=Path("knowledge"))
        self.submitted = []
        self.estimates = []

    def estimate(self, model, params):
        self.estimates.append((model, params))
        return 0.5

    def submit(self, model, params):
        self.submitted.append(params)
        return f"job-{len(self.submitted)}"

    def wait(self, job_id, **kw):
        return {"status": "completed"}

    def download(self, job_id, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n")
        return Path(dest)


class KeyedProvider(FakeProvider):
    """Фейк, ОБЪЯВЛЯЮЩИЙ переменную окружения с ключом, — как настоящий адаптер.

    Нужен, чтобы проверить D-2 (отсутствующий ключ отбивается до сметы) на том же
    коде, который исполняют wavespeed/runware/openrouter, а не на копии проверки.
    """
    name = "keyed"
    api_key_env = "KEYED_API_KEY"


def fake_provider(monkeypatch, cls=FakeProvider):
    fp = cls()
    monkeypatch.setattr(gb, "get_provider", lambda name, kd=None: fp)
    return fp


def run(proj, stage):
    return gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", stage, "--yes"])


def test_happy_path_storyboard(proj, monkeypatch):
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(fp.submitted) == 3
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "generated"
    assert (proj / "episodes" / "ep01" / "storyboard" / "001.png").exists()


def test_storyboard_passes_resolution(proj, monkeypatch):
    fp = fake_provider(monkeypatch)
    run(proj, "storyboard")
    assert fp.submitted[0]["resolution"] == "720p"


def test_storyboard_passes_image_tier(proj, monkeypatch):
    """tier из models.image пробрасывается в params раскадровки (находка B)."""
    fp = fake_provider(monkeypatch)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["image"]["tier"] = "hd"
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    run(proj, "storyboard")
    assert fp.submitted[0].get("tier") == "hd"


def test_resume_skips_generated(proj, monkeypatch):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp2.submitted == []


def accept_frames(proj, status="done"):
    m = Manifest(proj / "manifest.json")
    for item_id in list(m.data["items"]):
        if m.get(item_id)["status"] == "generated":
            m.set_status(item_id, status)
    m.save()


def test_segments_pass_start_end_frames(proj, monkeypatch):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    accept_frames(proj)
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(fp2.submitted) == 2
    assert "start_frame" in fp2.submitted[0]
    assert "end_frame" in fp2.submitted[0]
    assert fp2.submitted[0]["tier"] == "fast"
    assert fp2.submitted[0]["resolution"] == "720p"


def test_segment_without_end_frame_submits_only_start(proj, monkeypatch):
    # Без end_frame в плане провайдер не должен получать ключ вовсе: иначе модель
    # снова интерполирует между планами. Пустой end_frame тоже не годится —
    # адаптер отличает «нет ключа» от значения только по отсутствию.
    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    for s in shots["segments"]:
        s.pop("end_frame", None)
    (proj / "episodes" / "ep01" / "shots.json").write_text(
        json.dumps(shots, ensure_ascii=False), encoding="utf-8")
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    accept_frames(proj)
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "segments") == 0
    assert "start_frame" in fp2.submitted[0]
    assert "end_frame" not in fp2.submitted[0]


def test_segments_blocked_until_frames_accepted(proj, monkeypatch, capsys):
    fp = fake_provider(monkeypatch)
    run(proj, "storyboard")  # кадры в generated — ревью не пройдено
    capsys.readouterr()
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "segments") == 3
    assert fp2.estimates == []  # заблокировано ДО сметы и трат
    out = capsys.readouterr().out
    assert "заблокирована" in out
    assert "ep01/storyboard/001" in out


def test_segments_blocked_when_frames_never_generated(proj, monkeypatch, capsys):
    fake_provider(monkeypatch)
    assert run(proj, "segments") == 3  # storyboard вообще не запускался
    assert "не генерировался" in capsys.readouterr().out


def test_segments_pass_with_accepted_with_notes(proj, monkeypatch):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    accept_frames(proj, status="accepted_with_notes")
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "segments") == 0
    assert len(fp2.submitted) == 2


def test_skeleton_card_blocks_segments(proj, monkeypatch):
    fake_provider(monkeypatch)
    card = Path("knowledge/video/seedance_2_0.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run(proj, "segments") == 2  # валидация остановила ДО трат


def test_skeleton_image_card_blocks_storyboard(proj, monkeypatch):
    """skeleton image-карточка блокирует раскадровку ДО трат (гейт, симметрично видео)."""
    fp = fake_provider(monkeypatch)
    card = Path("knowledge/images/z_image.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run(proj, "storyboard") == 2
    assert fp.estimates == []  # валидация остановила ДО сметы


def test_image_model_not_on_provider_blocks_storyboard(proj, monkeypatch, capsys):
    """Image-модель не сконфигурирована под выбранного провайдера — блок раскадровки."""
    fake_provider(monkeypatch)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["image"]["provider"] = "runware"  # в карте только wavespeed
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    assert run(proj, "storyboard") == 2
    assert "runware" in capsys.readouterr().out


def test_model_not_on_provider_blocks_segments(proj, monkeypatch, capsys):
    """Если видео-модель не сконфигурирована под выбранного провайдера — блок."""
    fake_provider(monkeypatch)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["video"]["provider"] = "runware"  # в карте только wavespeed
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    assert run(proj, "segments") == 2
    assert "runware" in capsys.readouterr().out


def test_provider_preflight_blocks_segments_before_estimate(proj, monkeypatch, capsys):
    """Ревью-находка 1: смета не должна обещать цену, которую submit не может
    выполнить (напр. Runware не умеет разрешение проекта). Хук провайдера
    preflight_problems проверяется ДО сметы — до провайдера дело не доходит:
    estimate() не считается, submit() не вызывается, код возврата 2 — тот же
    путь, каким уже отбиваются карточки, не прошедшие валидацию."""
    fp = fake_provider(monkeypatch)
    monkeypatch.setattr(
        fp, "preflight_problems",
        lambda model, params: [f"{model}: неизвестное resolution {params.get('resolution')!r}"])
    assert run(proj, "segments") == 2
    assert fp.estimates == []
    assert fp.submitted == []
    out = capsys.readouterr().out
    assert "НЕ ПРОЙДЕНА" in out
    assert "seedance_2_0" in out


def test_provider_preflight_blocks_storyboard_before_estimate(proj, monkeypatch, capsys):
    """Симметрично сегментам: preflight-хук провайдера блокирует раскадровку
    ДО сметы, тем же кодом 2 и тем же форматом вывода."""
    fp = fake_provider(monkeypatch)
    monkeypatch.setattr(
        fp, "preflight_problems",
        lambda model, params: [f"{model}: неизвестное resolution {params.get('resolution')!r}"])
    assert run(proj, "storyboard") == 2
    assert fp.estimates == []
    assert fp.submitted == []
    out = capsys.readouterr().out
    assert "НЕ ПРОЙДЕНА" in out
    assert "z_image" in out


def test_provider_error_returns_to_pending(proj, monkeypatch):
    """Технический сбой ProviderError возвращает item в pending и main → 1."""
    fp = fake_provider(monkeypatch)
    monkeypatch.setattr(fp, "submit",
                        lambda m, p: (_ for _ in ()).throw(ProviderError("сеть упала")))
    assert run(proj, "storyboard") == 1
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "pending"
    assert m.get("ep01/storyboard/001")["attempts"] == 1


def test_retry_after_failure_runs_only_failed(proj, monkeypatch):
    fp = fake_provider(monkeypatch)
    monkeypatch.setattr(fp, "submit",
                        lambda m, p: (_ for _ in ()).throw(ProviderError("сбой")))
    run(proj, "storyboard")  # все вернулись в pending
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(fp2.submitted) == 3


def test_skeleton_blocks_before_estimate(proj, monkeypatch):
    fp = fake_provider(monkeypatch)
    card = Path("knowledge/video/seedance_2_0.md")
    card.write_text(card.read_text(encoding="utf-8")
                    .replace("status: verified", "status: skeleton"),
                    encoding="utf-8")
    assert run(proj, "segments") == 2
    assert fp.estimates == []  # estimate не должен вызываться


def test_recover_stuck_generating_item(proj, monkeypatch):
    """Элемент в generating после прерывания восстанавливается в pending."""
    m = Manifest(proj / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.save()
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp.submitted  # submit вызывался
    m2 = Manifest(proj / "manifest.json")
    assert m2.get("ep01/storyboard/001")["status"] == "generated"


def test_job_id_persisted_when_wait_fails(proj, monkeypatch):
    """Если submit прошёл, а wait упал — job_id сохраняется в манифесте."""
    fp = fake_provider(monkeypatch)
    monkeypatch.setattr(fp, "submit", lambda m, p: "job-abc123")
    monkeypatch.setattr(fp, "wait",
                        lambda job_id, **kw: (_ for _ in ()).throw(ProviderError("timeout")))
    assert run(proj, "storyboard") == 1
    m = Manifest(proj / "manifest.json")
    item = m.get("ep01/storyboard/001")
    assert item["status"] == "pending"
    assert item["job_id"] == "job-abc123"


def test_refs_resolved_against_project_dir(tmp_path, monkeypatch):
    """refs в shots.json — относительно папки проекта; в params должны быть
    пути, существующие от CWD (корень репо)."""
    pdir = tmp_path / "projects" / "pilot"
    ep = pdir / "episodes" / "ep01"
    ep.mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps({
        "name": "pilot", "type": "animated_series", "theme": "space cats",
        "audience": "6-9", "episodes": 1, "episode_duration_sec": 10,
        "models": {"image": {"model": "z_image", "provider": "wavespeed"},
                   "video": {"model": "seedance_2_0", "provider": "wavespeed"}},
    }), encoding="utf-8")
    ref_file = pdir / "bible" / "ref.png"
    ref_file.parent.mkdir(parents=True)
    ref_file.write_bytes(b"x")
    (ep / "shots.json").write_text(json.dumps({
        "episode": "ep01",
        "frames": [{"n": 1, "prompt": "{{style}} a"},
                   {"n": 2, "prompt": "{{style}} b", "refs": ["bible/ref.png"]}],
        "segments": [],
    }), encoding="utf-8")
    write_image_card(tmp_path)
    write_style_guide(pdir)
    write_script(pdir)
    monkeypatch.chdir(tmp_path)
    fp = fake_provider(monkeypatch)
    result = gb.main(["--project", str(pdir), "--episode", "ep01",
                      "--stage", "storyboard", "--yes"])
    assert result == 0
    submitted_with_refs = [p for p in fp.submitted if p.get("refs")]
    assert len(submitted_with_refs) == 1
    resolved_ref = submitted_with_refs[0]["refs"][0]
    assert Path(resolved_ref).exists(), (
        f"Ref '{resolved_ref}' не существует от CWD; "
        "refs должны резолвиться против project_dir")


def reject(proj, item_id, reason="не по сценарию"):
    m = Manifest(proj / "manifest.json")
    m.set_status(item_id, "rejected", reject_reason=reason)
    m.save()


def set_max_rejections(proj, value):
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["max_rejections"] = value
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")


def test_rejected_autorequeued_and_regenerated(proj, monkeypatch):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(fp2.submitted) == 1  # перегенерирован только отклонённый
    m = Manifest(proj / "manifest.json")
    item = m.get("ep01/storyboard/001")
    assert item["status"] == "generated"
    assert item["reject_count"] == 1


def test_reject_limit_blocks_regeneration(proj, monkeypatch, capsys):
    set_max_rejections(proj, 1)
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp2.submitted == []
    out = capsys.readouterr().out
    assert "ЛИМИТ ОТКЛОНЕНИЙ" in out
    assert "ep01/storyboard/001" in out
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "rejected"


def test_idle_run_reports_awaiting_review(proj, monkeypatch, capsys):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    capsys.readouterr()
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp2.submitted == []
    assert "ждут ревью" in capsys.readouterr().out


def test_max_rejections_zero_blocks_immediately(proj, monkeypatch, capsys):
    set_max_rejections(proj, 0)
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp2.submitted == []
    assert "ЛИМИТ ОТКЛОНЕНИЙ" in capsys.readouterr().out


def test_blocked_items_do_not_prevent_pending_generation(proj, monkeypatch, capsys):
    set_max_rejections(proj, 1)
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    reject(proj, "ep01/storyboard/001")  # reject_count=1 = лимит → blocked
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/storyboard/002", "rejected", reject_reason="r")
    m.set_status("ep01/storyboard/002", "pending")
    m.save()
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert len(fp2.submitted) == 1  # только 002
    out = capsys.readouterr().out
    assert "ЛИМИТ ОТКЛОНЕНИЙ" in out
    m2 = Manifest(proj / "manifest.json")
    assert m2.get("ep01/storyboard/001")["status"] == "rejected"
    assert m2.get("ep01/storyboard/002")["status"] == "generated"


def test_idle_run_all_done(proj, monkeypatch, capsys):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    m = Manifest(proj / "manifest.json")
    for item_id in list(m.data["items"]):
        m.set_status(item_id, "done")
    m.save()
    capsys.readouterr()
    fp2 = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp2.submitted == []
    assert "Всё уже сгенерировано" in capsys.readouterr().out


def test_segments_blocked_when_frame_rejected(proj, monkeypatch, capsys):
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/storyboard/001", "rejected", reject_reason="bad angle")
    m.save()
    assert run(proj, "segments") == 3
    assert "статус rejected" in capsys.readouterr().out


def test_ffmpeg_error_returns_to_pending_and_batch_continues(proj, monkeypatch):
    """FfmpegError (сбой ensure_png, например неконвертируемые байты) — тот же
    технический сбой, что ProviderError (спека §13): item -> pending, счётчик
    fail растёт, а батч не прерывается — остальные элементы обрабатываются."""
    fp = fake_provider(monkeypatch)
    real_ensure_png = gb.ensure_png

    def flaky_ensure_png(path):
        if Path(path).name == "001.png":
            raise FfmpegError("ffmpeg упал")
        return real_ensure_png(path)

    monkeypatch.setattr(gb, "ensure_png", flaky_ensure_png)
    assert run(proj, "storyboard") == 1
    assert len(fp.submitted) == 3  # батч не прервался — 002 и 003 тоже дошли

    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "pending"
    assert m.get("ep01/storyboard/002")["status"] == "generated"
    assert m.get("ep01/storyboard/003")["status"] == "generated"


def test_frames_are_normalized_to_png_segments_are_not(proj, monkeypatch):
    """ensure_png зовётся на кадрах и не зовётся на отрезках (там .mp4)."""
    calls = []
    monkeypatch.setattr(gb, "ensure_png", lambda p: calls.append(Path(p)))
    fake_provider(monkeypatch)
    run(proj, "storyboard")
    assert [p.name for p in calls] == ["001.png", "002.png", "003.png"]

    m = Manifest(proj / "manifest.json")
    for n in (1, 2, 3):
        m.set_status(f"ep01/storyboard/{n:03d}", "done")
    m.save()
    calls.clear()
    fake_provider(monkeypatch)
    run(proj, "segments")
    assert calls == []


def test_storyboard_rejects_frame_without_style_placeholder(proj, monkeypatch):
    """Кадр без {{style}} — потеря стиля на всю серию; отбиваем до трат."""
    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    shots["frames"][0]["prompt"] = "cat on a fence"
    (proj / "episodes" / "ep01" / "shots.json").write_text(json.dumps(shots),
                                                           encoding="utf-8")
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 2
    assert fp.submitted == [], "до провайдера дойти не должно"


def test_storyboard_expands_placeholders_and_records_sent_prompt(proj, monkeypatch):
    """Провайдер получает развёрнутый текст, а манифест хранит то, что реально ушло."""
    write_style_guide(proj)   # с content_sha: иначе гейт видит stale_self

    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    shots["frames"][0]["prompt"] = "{{style}} cat on a fence"
    (proj / "episodes" / "ep01" / "shots.json").write_text(json.dumps(shots),
                                                           encoding="utf-8")

    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 0
    assert fp.submitted[0]["prompt"] == "flat 2D cartoon cat on a fence"

    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["prompt_sent"] == "flat 2D cartoon cat on a fence"


def _character_card(proj, name, status="approved"):
    """Карточка персонажа с каноническим блоком внешности.

    Поправка задачи 6: версия хелпера из брифа не проставляла content_sha, из-за
    чего artifact_state видел approved-карточку как stale_self (тело не совпадает
    с хешем во frontmatter, которого там просто не было) и stage_gate("characters",
    ...) её не пропускал — падал бы каждый тест этого блока. Хеш считаем так же,
    как это делает tests/test_preprod.py.
    """
    body = f"<!-- canonical:appearance -->orange cat {name}<!-- /canonical:appearance -->"
    meta = {"kind": "character", "status": status}
    if status == "approved":
        meta["content_sha"] = body_sha(body)
    save_artifact(Artifact(path=proj / "bible" / "characters" / f"{name}.md",
                           meta=meta, body=body))


def _script(proj, episode, characters, body="сценарий"):
    """Одобренный script.md с явно объявленным составом серии.

    Поправка 1 задачи 6: stage_gate("characters"/"storyboard", ...) и гейт
    непринятых референсов в generate_batch читают состав серии из поля
    characters во frontmatter сценария (factory.preprod.episode_cast), а не по
    факту наличия карточек в bible/characters/. Без этого поля тесты брифа не
    объявляют состав и падают на собственном гейте — это то самое следствие
    поправки, о котором предупреждает задание.
    """
    meta = {"kind": "script", "status": "approved", "characters": list(characters),
            "content_sha": body_sha(body)}
    save_artifact(Artifact(path=proj / "episodes" / episode / "script.md",
                           meta=meta, body=body))


def test_characters_stage_generates_one_ref_per_card(proj, monkeypatch):
    _character_card(proj, "murzik")
    _character_card(proj, "barsik")
    _script(proj, "ep01", ["murzik", "barsik"])
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 0
    assert len(fp.submitted) == 2
    m = Manifest(proj / "manifest.json")
    assert m.get("bible/characters/murzik")["kind"] == "character_ref"
    assert (proj / "bible" / "characters" / "murzik-ref.png").exists()


def test_characters_stage_prompt_contains_appearance(proj, monkeypatch):
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fp = fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    assert "orange cat murzik" in fp.submitted[0]["prompt"]


def test_characters_stage_prompt_carries_project_style(proj, monkeypatch):
    """Референс персонажа обязан нести стиль проекта.

    Живой прогон 2026-09-02: без стиля в промпте модель нарисовала
    фотореалистичный 3D-рендер там, где style-guide требует плоский мультфильм,
    и вдобавок перепутала пол персонажа. Референс — визуальный якорь, на который
    ссылается КАЖДЫЙ кадр раскадровки (shots.json: refs), поэтому якорь не в том
    стиле портит весь эпизод, а не одну картинку. Кадры стиль получают через
    expand_prompt({{style}}), референсы не получали ничего.
    """
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fp = fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    prompt = fp.submitted[0]["prompt"]
    assert "flat 2D cartoon" in prompt        # блок canonical:style
    assert "orange cat murzik" in prompt      # блок canonical:appearance
    assert prompt.index("flat 2D cartoon") < prompt.index("orange cat murzik"),         "стиль идёт первым, как в промптах кадров"


def test_characters_stage_refuses_placeholders_in_style_block(proj, monkeypatch):
    """Плейсхолдер, забытый в canonical:style, уехал бы провайдеру буквально."""
    body = "<!-- canonical:style -->flat {{char:murzik}} cartoon<!-- /canonical:style -->"
    save_artifact(Artifact(
        path=proj / "bible" / "style-guide.md",
        meta={"kind": "style-guide", "status": "approved",
              "content_sha": body_sha(body)}, body=body))
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 2
    assert fp.submitted == []  # отказ ДО трат


def test_characters_stage_blocked_without_cards(proj, monkeypatch):
    """Состав объявлен, карточек нет — гейт закрыт. Пустой состав (заставка,
    титры) законен и стадию не блокирует, поэтому объявляем персонажа явно."""
    write_script(proj, characters=["murzik"])
    """Ни сценария, ни карточек — гейт закрывает стадию через stage_gate
    (episodes/ep01/script.md не существует), а не через литеральную проверку "нет
    ни одной карточки" из брифа: та убрана поправкой 1, потому что серия без
    персонажей (заставка, титры) — законный случай, который эта проверка
    ломала бы."""
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 3
    assert fp.submitted == []  # заблокировано ДО сметы и трат


def test_characters_stage_ignores_cards_outside_episode_cast(proj, monkeypatch):
    """Поправка 2: референсы генерируются по составу ИМЕННО этой серии
    (episode_cast), а не по всем карточкам bible/characters/ — иначе персонаж
    другой серии оплатился бы заодно."""
    _character_card(proj, "murzik")
    _character_card(proj, "barsik")  # карточка есть, но не в составе ep01
    _script(proj, "ep01", ["murzik"])
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 0
    assert len(fp.submitted) == 1
    m = Manifest(proj / "manifest.json")
    assert "bible/characters/barsik" not in m.data["items"]


def test_characters_stage_normalizes_to_png(proj, monkeypatch):
    """Референс — такой же скачанный файл, как кадр раскадровки: провайдер может
    отдать не-PNG под именем .png (CLAUDE.md), поэтому ensure_png зовётся и для
    character_ref, не только для frame."""
    calls = []
    monkeypatch.setattr(gb, "ensure_png", lambda p: calls.append(Path(p)))
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 0
    assert calls == [proj / "bible" / "characters" / "murzik-ref.png"]


def test_characters_stage_idle_after_acceptance(proj, monkeypatch):
    """Повторный запуск после принятия референса ревью ничего не генерирует
    заново: manifest.add идемпотентен (setdefault) — тот же механизм, что и для
    кадров раскадровки."""
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()
    fp2 = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 0
    assert fp2.submitted == []


def test_storyboard_blocked_until_character_refs_accepted(proj, monkeypatch):
    """Кадры нельзя генерировать, пока референс персонажа не принят ревью."""
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    # референс сгенерирован, но не принят
    fp2 = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "storyboard", "--yes"]) == 3
    assert fp2.submitted == []  # до кадров дело не дошло — заблокировано раньше


def test_storyboard_ignores_uncast_character_refs(proj, monkeypatch):
    """Поправка 2: гейт storyboard проверяет референсы состава ИМЕННО этой серии
    (episode_cast) — персонаж, не объявленный в сценарии серии, чей референс не
    готов (или не существует вовсе), раскадровку не блокирует."""
    _character_card(proj, "murzik")
    _character_card(proj, "barsik")  # не в составе ep01
    _script(proj, "ep01", ["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()
    fp2 = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "storyboard", "--yes"]) == 0


def test_characters_stage_rejects_placeholder_in_appearance(proj, monkeypatch):
    body = ("<!-- canonical:appearance -->orange {{style}} cat"
            "<!-- /canonical:appearance -->")
    save_artifact(Artifact(path=proj / "bible" / "characters" / "murzik.md",
                           meta={"kind": "character", "status": "approved",
                                 "content_sha": body_sha(body)}, body=body))
    write_script(proj, characters=["murzik"])
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 2
    assert fp.submitted == []


def test_storyboard_blocked_when_character_card_changed_after_reference(proj, monkeypatch):
    """Правка внешности после приёмки референса делает картинку устаревшей:
    кадры сгенерировались бы по описанию, которого уже нет."""
    write_character(proj, "murzik")
    write_script(proj, characters=["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()

    art = load_artifact(proj / "bible" / "characters" / "murzik.md")
    art.body = ("<!-- canonical:appearance -->СЕРЫЙ кот"
                "<!-- /canonical:appearance -->")
    art.meta["content_sha"] = art.sha
    save_artifact(art)

    assert run(proj, "storyboard") == 3


def test_stale_reference_can_actually_be_requeued(proj, monkeypatch):
    """У гейта устаревшего референса обязан быть выход, который он называет.

    Гейт советует `review.py requeue`, но принятый референс лежит в `done`, а
    `done` задумывался терминальным — совет был невыполним, и проект вставал
    намертво: раскадровка заблокирована, а разблокировать нечем, кроме правки
    manifest.json руками (находка задачи 8f-B). Терминальность `done` защищала
    от переработки принятого — она появилась раньше, чем `card_sha` научился
    делать принятое устаревшим.
    """
    write_character(proj, "murzik")
    write_script(proj, characters=["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()

    art = load_artifact(proj / "bible" / "characters" / "murzik.md")
    art.body = ("<!-- canonical:appearance -->СЕРЫЙ кот"
                "<!-- /canonical:appearance -->")
    art.meta["content_sha"] = art.sha
    save_artifact(art)
    assert run(proj, "storyboard") == 3

    # Ровно то, что советует сообщение гейта.
    assert review.main(["--project", str(proj), "requeue",
                        "bible/characters/murzik"]) == 0
    # Референс перегенерирован и принят заново — раскадровка разблокирована.
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    m.save()
    assert run(proj, "storyboard") == 0


def test_segments_reject_stray_placeholder(proj, monkeypatch):
    """Отрезки плейсхолдеры не разворачивают, поэтому {{style}} в промпте движения
    уехал бы провайдеру буквально и оплатился мусором. Отбиваем до сметы."""
    shots = json.loads((proj / "episodes" / "ep01" / "shots.json").read_text(
        encoding="utf-8"))
    shots["segments"][0]["prompt"] = "{{style}} cat walks"
    (proj / "episodes" / "ep01" / "shots.json").write_text(json.dumps(shots),
                                                           encoding="utf-8")
    m = Manifest(proj / "manifest.json")
    for n in (1, 2, 3):
        item_id = f"ep01/storyboard/{n:03d}"
        m.add(item_id, kind="frame")
        for status in ("generating", "generated", "done"):
            m.set_status(item_id, status)
    m.save()
    fp = fake_provider(monkeypatch)
    assert run(proj, "segments") == 2
    assert fp.submitted == [], "до провайдера дойти не должно"


def test_budget_ceiling_prints_four_decimals(proj, monkeypatch, capsys):
    """D-6: потолок бюджета печатается с тем же числом знаков после запятой, что
    смета и остаток (четыре) — на маленьких сметах двузначный потолок выглядел
    нулевым (budget_usd: 0.002 печатался как 'потолок 0.00')."""
    fake_provider(monkeypatch)
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["autonomy"] = "full"
    pj["budget_usd"] = 0.002
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")

    assert run(proj, "storyboard") == 3
    out = capsys.readouterr().out
    assert "потолок 0.0020" in out


def _add_ref_to_shots(proj, ref="bible/characters/murzik-ref.png"):
    """Дописать первому кадру ссылку на файл референса (которого нет на диске)."""
    path = proj / "episodes" / "ep01" / "shots.json"
    shots = json.loads(path.read_text(encoding="utf-8"))
    shots["frames"][0]["refs"] = [ref]
    path.write_text(json.dumps(shots), encoding="utf-8")


def test_missing_ref_file_is_code_2_without_traceback(proj, monkeypatch, capsys):
    """D-4: shots.json ссылается на несуществующий файл референса. Это ошибка
    контракта входных данных стадии — код 2 и внятное сообщение, а не
    необработанный ShotsError (единственный нечеловекочитаемый вывод первого
    живого прогона) и не код 1 «технический сбой»."""
    _add_ref_to_shots(proj)
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 2
    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert "murzik-ref.png" in out
    assert fp.estimates == [], "остановка ДО сметы"


def test_storyboard_gate_speaks_before_shots_are_loaded(proj, monkeypatch, capsys):
    """D-5: референс персонажа не принят, файла *-ref.png на диске ещё нет.
    Гейт стадии идёт ДО load_shots, поэтому человек получает объяснение про
    референс, а не падение загрузчика на отсутствующем файле."""
    _character_card(proj, "murzik")
    _script(proj, "ep01", ["murzik"])
    _add_ref_to_shots(proj)
    fp = fake_provider(monkeypatch)
    assert run(proj, "storyboard") == 3
    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert "референс" in out
    assert "missing ref" not in out, "гейт обязан сработать раньше load_shots"
    assert fp.estimates == []


def test_missing_provider_key_blocks_before_estimate(proj, monkeypatch, capsys):
    """D-2: провайдер объявил api_key_env, переменной в окружении нет. Это ошибка
    конфигурации, известная до первого байта в сеть: код 2 до сметы и до вопроса
    [y/N], одной строкой на батч, без роста attempts в манифесте."""
    monkeypatch.delenv("KEYED_API_KEY", raising=False)
    fp = fake_provider(monkeypatch, KeyedProvider)
    assert run(proj, "storyboard") == 2
    out = capsys.readouterr().out
    assert "KEYED_API_KEY" in out
    assert "СМЕТА" not in out
    assert fp.estimates == []
    assert fp.submitted == []
    m = Manifest(proj / "manifest.json")
    with pytest.raises(ManifestError):
        m.get("ep01/storyboard/001")  # попытка генерации не расходовалась


def test_present_provider_key_lets_run_through(proj, monkeypatch):
    """Обратная сторона D-2: объявленный ключ, который есть в окружении, ничего
    не блокирует — проверка отбивает отсутствие ключа, а не сам факт объявления."""
    monkeypatch.setenv("KEYED_API_KEY", "test-key")
    fp = fake_provider(monkeypatch, KeyedProvider)
    assert run(proj, "storyboard") == 0
    assert len(fp.submitted) == 3


def test_broken_project_json_is_refused_before_estimate(proj, monkeypatch, capsys):
    """Регресс-страховка, найденная финальным ревью ветки: непригодный бриф ронял
    платную стадию трейсбеком с кодом 1 «технический сбой», хотя это отказ по
    контракту входных данных — тот же класс, что D-4."""
    (proj / "project.json").write_text('{"name": "p", "type": "animated_series"}',
                                       encoding="utf-8")
    fp = fake_provider(monkeypatch)
    assert gb.main(["--project", str(proj), "--episode", "ep01",
                    "--stage", "characters", "--yes"]) == 2
    out = capsys.readouterr().out
    assert "project.json" in out and "Traceback" not in out, out
    assert fp.submitted == []


def test_old_manifest_without_card_sha_does_not_block(proj, monkeypatch):
    """Обещание обратной совместимости: манифесты, записанные до появления
    card_sha, поля не содержат, и старые проекты не должны блокироваться задним
    числом. Ни один другой тест эту ветку не проходит — все они идут через новый
    код генерации, который card_sha всегда пишет."""
    write_character(proj, "murzik")
    write_script(proj, characters=["murzik"])
    fake_provider(monkeypatch)
    gb.main(["--project", str(proj), "--episode", "ep01",
             "--stage", "characters", "--yes"])
    m = Manifest(proj / "manifest.json")
    m.set_status("bible/characters/murzik", "done")
    del m.data["items"]["bible/characters/murzik"]["card_sha"]   # манифест «до»
    m.save()

    art = load_artifact(proj / "bible" / "characters" / "murzik.md")
    art.body = "<!-- canonical:appearance -->СЕРЫЙ кот<!-- /canonical:appearance -->"
    art.meta["content_sha"] = art.sha
    save_artifact(art)
    assert run(proj, "storyboard") == 0, "старый манифест блокировать нельзя"


# --- стадии звука (дизайн 2026-09-04 §5) ---

TTS_CARD = (
    "---\nid: tts_x\ntype: audio\naudio_kind: tts\nstatus: verified\n"
    "language_map: {ru: \"Russian (Russia)\"}\n"
    "providers:\n"
    "  wavespeed: { id: \"v/tts\", usd_per_image: 0.02,"
    " fields: { text: text, language: language, voice: voice } }\n"
    "---\n# tts\n")
SFX_CARD = (
    "---\nid: sfx_x\ntype: audio\naudio_kind: sfx\nstatus: verified\n"
    "providers:\n"
    "  wavespeed: { id: \"v/sfx\", usd_per_image: 0.01,"
    " fields: { prompt: text_prompt, duration: duration } }\n"
    "---\n# sfx\n")
MUSIC_CARD = (
    "---\nid: music_x\ntype: audio\naudio_kind: music\nstatus: verified\n"
    "providers:\n"
    "  wavespeed: { id: \"v/music\", usd_per_image: 0.003,"
    " fields: { prompt: prompt, duration: duration } }\n"
    "---\n# music\n")
FOLEY_CARD_GB = (
    "---\nid: foley_x\ntype: audio\naudio_kind: foley\nstatus: verified\n"
    "providers:\n"
    "  wavespeed: { id: \"v/foley\", usd_per_image: 0.001,"
    " fields: { prompt: prompt, video: video, duration: duration } }\n"
    "---\n# foley\n")
LIPSYNC_CARD = (
    "---\nid: lip_x\ntype: audio\naudio_kind: lipsync\nstatus: verified\n"
    "providers:\n"
    "  wavespeed: { id: \"v/lip\", usd_per_image: 0.075,"
    " fields: { video: video, audio: audio } }\n"
    "---\n# lipsync\n")


def enable_audio(proj):
    """Карточки моделей звука + блок models.audio в project.json."""
    adir = Path("knowledge") / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    for name, card in (("tts_x", TTS_CARD), ("sfx_x", SFX_CARD),
                       ("music_x", MUSIC_CARD), ("foley_x", FOLEY_CARD_GB),
                       ("lip_x", LIPSYNC_CARD)):
        (adir / f"{name}.md").write_text(card, encoding="utf-8")
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["language"] = "ru"
    pj["models"]["audio"] = {
        "tts": {"model": "tts_x", "provider": "wavespeed"},
        "sfx": {"model": "sfx_x", "provider": "wavespeed"},
        "music": {"model": "music_x", "provider": "wavespeed"},
        "foley": {"model": "foley_x", "provider": "wavespeed"},
        "lipsync": {"model": "lip_x", "provider": "wavespeed"},
    }
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")


def write_audio_plan(proj, plan):
    (proj / "episodes" / "ep01" / "audio.json").write_text(
        json.dumps(plan), encoding="utf-8")


PLAN = {
    "voice_lines": [{"id": "vl-01", "speaker": "Устинья", "voice": "Kore",
                     "text": "Так.", "direction": "flat, no emotion",
                     "segment": 1, "offset": 0.5}],
    "music_cues": [{"id": "mus-01", "prompt": "cold sea", "duration": 10,
                    "segment": 1, "offset": 0}],
    "sfx": [{"id": "sfx-01", "prompt": "boat horn", "duration": 3,
             "segment": 2, "offset": 1.0}],
}


def test_audio_stage_submits_all_three_lists(proj, monkeypatch):
    enable_audio(proj)
    write_audio_plan(proj, PLAN)
    fp = fake_provider(monkeypatch)
    assert run(proj, "audio") == 0
    assert len(fp.submitted) == 3
    tts = next(s for s in fp.submitted if "text" in s)
    # подача и текст склеиваются ТИРЕ — живая проба 2026-09-04
    assert tts["text"] == "flat, no emotion — Так."
    assert tts["voice"] == "Kore"
    # язык — в том виде, в каком его хочет модель, из language_map карточки
    assert tts["language"] == "Russian (Russia)"


def test_audio_stage_without_direction_sends_plain_text(proj, monkeypatch):
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    del plan["voice_lines"][0]["direction"]
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)
    fp = fake_provider(monkeypatch)
    assert run(proj, "audio") == 0
    assert fp.submitted[0]["text"] == "Так."


def test_audio_stage_missing_plan_is_contract_error(proj, monkeypatch):
    enable_audio(proj)
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 2


def test_audio_stage_without_models_audio_block(proj, monkeypatch, capsys):
    write_audio_plan(proj, PLAN)
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 2
    assert "models.audio" in capsys.readouterr().out


def test_foley_blocked_until_segments_accepted(proj, monkeypatch, capsys):
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["foley"] = [{"id": "fol-01", "segment": 1, "prompt": "boots on iron"}]
    write_audio_plan(proj, plan)
    fake_provider(monkeypatch)
    assert run(proj, "foley") == 3
    assert "ОТРЕЗКИ НЕ ПРИНЯТЫ" in capsys.readouterr().out


def test_lipsync_blocked_until_voice_exists(proj, monkeypatch, capsys):
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["voice_lines"][0]["lipsync"] = True
    write_audio_plan(proj, plan)
    # отрезок принят, но голоса ещё нет
    m = Manifest(proj / "manifest.json")
    m.add("ep01/segments/001", kind="segment")
    m.set_status("ep01/segments/001", "generating")
    m.set_status("ep01/segments/001", "generated")
    m.set_status("ep01/segments/001", "done")
    m.save()
    fake_provider(monkeypatch)
    assert run(proj, "lipsync") == 3
    assert "ЕЩЁ НЕ ОЗВУЧЕНЫ" in capsys.readouterr().out


def test_foley_job_carries_segment_video_and_duration(proj, monkeypatch):
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["foley"] = [{"id": "fol-01", "segment": 1, "prompt": "boots on iron"}]
    plan["voice_lines"] = []
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)
    m = Manifest(proj / "manifest.json")
    m.add("ep01/segments/001", kind="segment")
    m.set_status("ep01/segments/001", "generating")
    m.set_status("ep01/segments/001", "generated")
    m.set_status("ep01/segments/001", "done")
    m.save()
    fp = fake_provider(monkeypatch)
    assert run(proj, "foley") == 0
    sent = fp.submitted[0]
    assert sent["video"].endswith("001.mp4")
    # длительность фоли задаёт отрезок, а не план: короче — дыра, длиннее — залезет
    assert sent["duration"] == 5
    assert "prompt" in sent


def test_lipsync_writes_separate_file(proj, monkeypatch):
    # Исходный отрезок не перезаписывается: неудачный дубль не должен уничтожать
    # оплаченное видео.
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["voice_lines"][0]["lipsync"] = True
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)
    ep = proj / "episodes" / "ep01"
    (ep / "audio").mkdir(parents=True, exist_ok=True)
    (ep / "audio" / "vl-01.mp3").write_bytes(b"voice")
    m = Manifest(proj / "manifest.json")
    m.add("ep01/segments/001", kind="segment")
    m.set_status("ep01/segments/001", "generating")
    m.set_status("ep01/segments/001", "generated")
    m.set_status("ep01/segments/001", "done")
    m.save()
    fake_provider(monkeypatch)
    assert run(proj, "lipsync") == 0
    assert (ep / "segments" / "001-lipsync.mp4").exists()
    assert not (ep / "segments" / "001.mp4").exists()  # исходника и не было


DUAL_SFX_CARD = """---
id: sfx_dual
type: audio
audio_kind: sfx
status: verified
providers:
  wavespeed: { id: "w/sfx", usd_per_image: 0.01, fields: { prompt: text_prompt, duration: duration } }
  runware: { id: "r/sfx", usd_per_image: 0.02, fields: { prompt: text_prompt, duration: duration } }
---
# dual
"""

def test_audio_roles_on_different_providers_refused(proj, monkeypatch, capsys):
    # Стадия ходит к одному провайдеру: молча взять первого попавшегося значило бы
    # слать запросы одной модели по адресу другой. Карточка объявлена у ОБОИХ,
    # поэтому раньше срабатывает не проверка доступности, а именно эта.
    enable_audio(proj)
    (Path("knowledge") / "audio" / "sfx_dual.md").write_text(
        DUAL_SFX_CARD, encoding="utf-8")
    pj = json.loads((proj / "project.json").read_text(encoding="utf-8"))
    pj["models"]["audio"]["sfx"] = {"model": "sfx_dual", "provider": "runware"}
    (proj / "project.json").write_text(json.dumps(pj), encoding="utf-8")
    write_audio_plan(proj, PLAN)
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 2
    assert "разных" in capsys.readouterr().out


def test_empty_audio_plan_is_not_an_error(proj, monkeypatch, capsys):
    enable_audio(proj)
    write_audio_plan(proj, {})
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 0
    assert "пуст" in capsys.readouterr().out


def test_voice_process_applied_after_download(proj, monkeypatch):
    """Реплика с process обрабатывается сразу после скачивания.

    По карточке Гвоздь говорит голосом Устиньи с жестяным призвуком: второй голос
    не нужен, нужен тот же, обработанный. Обработка детерминирована, поэтому
    делается кодом, а не уговорами модели.
    """
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["voice_lines"][0]["process"] = "tin"
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)
    calls = []
    monkeypatch.setattr(gb, "apply_voice_process",
                        lambda src, dest, name: calls.append(name) or Path(dest))
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 0
    assert calls == ["tin"]


def test_voice_without_process_is_not_touched(proj, monkeypatch):
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)
    calls = []
    monkeypatch.setattr(gb, "apply_voice_process",
                        lambda src, dest, name: calls.append(name))
    fake_provider(monkeypatch)
    assert run(proj, "audio") == 0
    assert calls == []


def test_script_runs_as_main(proj):
    """Скрипт обязан работать при ПРЯМОМ запуске, а не только при импорте.

    Ревью 2026-09-05: рефакторинг вынес _run_jobs в конец файла, ниже блока
    `if __name__ == "__main__"`, и CLI падал NameError. Тесты этого не видели,
    потому что импорт модуля выполняет файл целиком — порядок определений при
    импорте не важен, а при запуске важен. Ловится только настоящим запуском.
    """
    import subprocess
    import sys
    script = Path(gb.__file__).resolve()
    out = subprocess.run(
        [sys.executable, str(script), "--project", str(proj),
         "--episode", "ep01", "--stage", "storyboard", "--yes"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=Path.cwd(), timeout=120)
    assert "NameError" not in (out.stdout + out.stderr), out.stdout + out.stderr


def test_failed_voice_process_keeps_paid_original(proj, monkeypatch):
    """Сбой обработки не должен уничтожать ОПЛАЧЕННУЮ реплику.

    Ревью 2026-09-05: безусловный unlink в finally стирал исходник, статус
    уходил в pending без учёта трат, и следующий запуск платил второй раз.
    """
    from factory.ffmpeg_tools import FfmpegError
    enable_audio(proj)
    plan = json.loads(json.dumps(PLAN))
    plan["voice_lines"][0]["process"] = "tin"
    plan["music_cues"] = []
    plan["sfx"] = []
    write_audio_plan(proj, plan)

    def boom(src, dest, name):
        raise FfmpegError("ffmpeg упал")

    monkeypatch.setattr(gb, "apply_voice_process", boom)
    fake_provider(monkeypatch)
    run(proj, "audio")
    voice = proj / "episodes" / "ep01" / "audio" / "vl-01.mp3"
    assert voice.exists(), "оплаченный исходник уничтожен"
    assert not voice.with_name("vl-01-raw.mp3").exists(), "временный файл остался"
