"""Тесты батч-генератора generate_batch.py (спека §8; мультипровайдерный слой).

Провайдер замокан фейком (gb.get_provider). Стадия audio удалена (вынесена в
отдельную задачу — генерация звука на ElevenLabs).
"""
import json
from pathlib import Path

import pytest

import generate_batch as gb
from factory.ffmpeg_tools import FfmpegError
from factory.manifest import Manifest
from factory.providers.base import ProviderError

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
        "frames": [{"n": 1, "prompt": "a"}, {"n": 2, "prompt": "b"},
                   {"n": 3, "prompt": "c"}],
        "segments": [
            {"n": 1, "start_frame": 1, "end_frame": 2, "prompt": "m1"},
            {"n": 2, "start_frame": 2, "end_frame": 3, "prompt": "m2"}],
    }), encoding="utf-8")
    kdir = tmp_path / "knowledge" / "video"
    kdir.mkdir(parents=True)
    (kdir / "seedance_2_0.md").write_text(VIDEO_CARD, encoding="utf-8")
    write_image_card(tmp_path)
    monkeypatch.chdir(tmp_path)
    return pdir


class FakeProvider:
    """Замена реального провайдера: фиксирует submit-параметры, пишет файлы."""
    unit = "$"

    def __init__(self):
        self.submitted = []
        self.estimates = []

    def preflight_problems(self, model, params):
        """По умолчанию у фейка нечего проверять — как и у BaseHTTPProvider."""
        return []

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


def fake_provider(monkeypatch):
    fp = FakeProvider()
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
    assert "НЕ ПРОШЛА ВАЛИДАЦИЮ" in out
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
    assert "НЕ ПРОШЛА ВАЛИДАЦИЮ" in out
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
        "frames": [{"n": 1, "prompt": "a"},
                   {"n": 2, "prompt": "b", "refs": ["bible/ref.png"]}],
        "segments": [],
    }), encoding="utf-8")
    write_image_card(tmp_path)
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
