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
