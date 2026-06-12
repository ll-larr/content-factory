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
    m.set_status("x", "generated", file="x.png")
    m.set_status("x", "done")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")


def test_rejected_requires_reason(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    m.set_status("x", "generated")
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
    m.set_status("a", "generated", file="a.png", credits_spent=2.0)
    m.set_status("a", "done")
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
        m.set_status("x", "generated", fiel="typo.png")


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


def review_ready(m, item_id="x", kind="frame"):
    """Довести item до generated (готов к ревью)."""
    m.add(item_id, kind=kind)
    m.set_status(item_id, "generating")
    m.set_status(item_id, "generated", file=f"{item_id}.png")


def test_generation_ends_in_generated_then_review_accepts(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    assert m.get("x")["status"] == "generated"
    m.set_status("x", "done")  # ревью: принято
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "pending")  # done терминален


def test_generating_to_done_directly_is_forbidden(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "done")


def test_generating_to_rejected_directly_is_forbidden(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    m.add("x", kind="frame")
    m.set_status("x", "generating")
    with pytest.raises(ManifestError, match="not allowed"):
        m.set_status("x", "rejected", reject_reason="r")


def test_reject_count_increments_automatically(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    assert m.get("x")["reject_count"] == 0
    m.set_status("x", "rejected", reject_reason="anatomy")
    assert m.get("x")["reject_count"] == 1
    m.set_status("x", "pending")
    m.set_status("x", "generating")
    m.set_status("x", "generated")
    m.set_status("x", "rejected", reject_reason="style")
    assert m.get("x")["reject_count"] == 2


def test_accepted_with_notes_allows_requeue(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    review_ready(m)
    m.set_status("x", "accepted_with_notes", notes="фон темноват")
    m.set_status("x", "pending")
    assert m.get("x")["status"] == "pending"
