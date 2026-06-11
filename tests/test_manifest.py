import pytest
from factory.manifest import Manifest, ManifestError


def test_add_is_idempotent(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("ep01/storyboard/001", kind="frame")
    m.set_status("ep01/storyboard/001", "generating")
    m.add("ep01/storyboard/001", kind="frame")  # повторное add не сбрасывает статус
    assert m.get("ep01/storyboard/001")["status"] == "generating"


def test_done_is_terminal(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    m.set_status("x", "done", file="x.png")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")


def test_rejected_requires_reason(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="reject_reason"):
        m.set_status("x", "rejected")
    m.set_status("x", "rejected", reject_reason="anatomy: extra fingers")
    m.set_status("x", "pending")  # перегенерация разрешена


def test_pending_filter_and_persistence(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest(path)
    m.add("a", kind="frame")
    m.add("b", kind="segment")
    m.set_status("a", "generating")
    m.set_status("a", "done", file="a.png", credits_spent=2.0)
    m.save()

    m2 = Manifest(path)  # перечитываем с диска
    assert m2.pending() == ["b"]
    assert m2.pending(kind="frame") == []
    assert m2.credits_total() == 2.0


def test_get_unknown_id_raises(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    with pytest.raises(ManifestError, match="unknown item_id"):
        m.get("nope")


def test_unknown_field_raises(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="unknown fields"):
        m.set_status("x", "done", fiel="typo.png")


def test_crash_resume_generating_to_pending(tmp_path):
    path = tmp_path / "manifest.json"
    m = Manifest(path)
    m.add("x", kind="segment")
    m.set_status("x", "generating")
    m.save()
    # «упали», перезапустились: вернуть зависший item в очередь
    m2 = Manifest(path)
    assert m2.get("x")["status"] == "generating"
    m2.set_status("x", "pending")
    assert m2.pending() == ["x"]
