"""Тесты review-CLI (спека ревью §5)."""
import json

import pytest

import review
from factory.manifest import Manifest


@pytest.fixture
def proj(tmp_path):
    """Проект с манифестом: 001 в generated (ждёт ревью), 002 в pending."""
    pdir = tmp_path / "projects" / "pilot"
    pdir.mkdir(parents=True)
    m = Manifest(pdir / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.set_status("ep01/storyboard/001", "generated", file="001.png")
    m.add("ep01/storyboard/002", kind="frame")
    m.save()
    return pdir


def run(proj, *args):
    return review.main(["--project", str(proj), *args])


def test_accept_moves_generated_to_done(proj):
    assert run(proj, "accept", "ep01/storyboard/001") == 0
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "done"


def test_accept_is_all_or_nothing(proj, capsys):
    # 002 в pending -> переход запрещён; 001 НЕ должен сохраниться как done
    assert run(proj, "accept", "ep01/storyboard/001",
               "ep01/storyboard/002") == 1
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "generated"
    err = capsys.readouterr().err
    assert "not allowed" in err
    assert "Ни один из переходов не сохранён" in err


def test_accept_notes(proj):
    assert run(proj, "accept-notes", "ep01/storyboard/001",
               "--notes", "фон темноват") == 0
    m = Manifest(proj / "manifest.json")
    it = m.get("ep01/storyboard/001")
    assert it["status"] == "accepted_with_notes"
    assert it["notes"] == "фон темноват"


def test_reject_records_reason_and_count(proj):
    assert run(proj, "reject", "ep01/storyboard/001",
               "--reason", "anatomy") == 0
    m = Manifest(proj / "manifest.json")
    it = m.get("ep01/storyboard/001")
    assert it["status"] == "rejected"
    assert it["reject_reason"] == "anatomy"
    assert it["reject_count"] == 1


def test_reject_without_reason_fails(proj):
    with pytest.raises(SystemExit):  # argparse: --reason обязателен
        run(proj, "reject", "ep01/storyboard/001")


def test_requeue_works_even_past_limit(proj):
    m = Manifest(proj / "manifest.json")
    m.set_status("ep01/storyboard/001", "rejected", reject_reason="r1")
    m.data["items"]["ep01/storyboard/001"]["reject_count"] = 5  # за лимитом
    m.save()
    assert run(proj, "requeue", "ep01/storyboard/001") == 0
    m2 = Manifest(proj / "manifest.json")
    it = m2.get("ep01/storyboard/001")
    assert it["status"] == "pending"
    assert it["reject_count"] == 5  # журнал не сбрасывается


def test_unknown_id_returns_1(proj, capsys):
    assert run(proj, "accept", "nope") == 1
    assert "unknown item_id" in capsys.readouterr().err


def test_list_with_status_filter(proj, capsys):
    assert run(proj, "list", "--status", "generated") == 0
    out = capsys.readouterr().out
    assert "ep01/storyboard/001" in out
    assert "ep01/storyboard/002" not in out


def test_list_shows_all_without_filter(proj, capsys):
    assert run(proj, "list") == 0
    out = capsys.readouterr().out
    assert "ep01/storyboard/001" in out
    assert "ep01/storyboard/002" in out


def test_requeue_from_generated_is_forbidden(proj, capsys):
    # generated -> pending не входит в машину статусов: сначала ревью
    assert run(proj, "requeue", "ep01/storyboard/001") == 1
    assert "not allowed" in capsys.readouterr().err
    m = Manifest(proj / "manifest.json")
    assert m.get("ep01/storyboard/001")["status"] == "generated"


def test_list_on_missing_manifest_is_empty(tmp_path, capsys):
    pdir = tmp_path / "projects" / "empty"
    pdir.mkdir(parents=True)
    assert run(pdir, "list") == 0
    assert capsys.readouterr().out == ""


def test_list_on_legacy_manifest_without_reject_count(tmp_path, capsys):
    """Старые манифесты (фаза 1) не имеют reject_count — list не падает (спека §7)."""
    pdir = tmp_path / "projects" / "legacy"
    pdir.mkdir(parents=True)
    legacy = {"items": {"ep01/storyboard/001": {
        "kind": "frame", "status": "done", "attempts": 1,
        "credits_spent": 1.5, "file": "001.png", "job_id": "j1",
        "reject_reason": None, "notes": None}}}
    (pdir / "manifest.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert run(pdir, "list") == 0
    out = capsys.readouterr().out
    assert "ep01/storyboard/001" in out
    assert "reject_count=0" in out
