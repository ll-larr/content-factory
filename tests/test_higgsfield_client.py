"""Тесты адаптера Higgsfield CLI (scripts/factory/higgsfield_client.py)."""
import json
import pytest
from factory import higgsfield_client as hf


def patch_run(monkeypatch, stdout="{}", returncode=0, stderr=""):
    calls = []

    class P:
        pass

    def fake_run(args, capture_output, text):
        calls.append(args)
        p = P()
        p.returncode, p.stdout, p.stderr = returncode, stdout, stderr
        return p

    monkeypatch.setattr(hf.subprocess, "run", fake_run)
    return calls


def test_estimate_parses_exact_credits(monkeypatch):
    patch_run(monkeypatch, stdout=json.dumps({"credits": 4, "credits_exact": 4.8}))
    assert hf.estimate("seedance1_5", {"prompt": "x"}) == 4.8


def test_estimate_fallback_to_credits(monkeypatch):
    """Если credits_exact отсутствует — возвращаем credits."""
    patch_run(monkeypatch, stdout=json.dumps({"credits": 4}))
    assert hf.estimate("seedance1_5", {"prompt": "x"}) == 4


def test_submit_returns_first_job_id_and_calls_cli(monkeypatch):
    calls = patch_run(monkeypatch, stdout=json.dumps(["j-1"]))
    assert hf.submit("nano_banana_flash", {"prompt": "x"}) == "j-1"
    import os
    assert os.path.basename(calls[0][0]).lower().startswith("higgsfield")  # вызван именно CLI
    assert "--json" in calls[0]


def test_submit_empty_array_raises(monkeypatch):
    """Пустой массив job_id → HiggsfieldError."""
    patch_run(monkeypatch, stdout=json.dumps([]))
    with pytest.raises(hf.HiggsfieldError):
        hf.submit("nano_banana_flash", {"prompt": "x"})


def test_media_params_become_flags(monkeypatch):
    calls = patch_run(monkeypatch, stdout=json.dumps(["j-1"]))
    hf.submit("kling3_0", {
        "prompt": "m", "start_frame": "a.png", "end_frame": "b.png",
        "refs": ["r1.png", "r2.png"], "duration": 5})
    args = calls[0]
    assert args[args.index("--start-image") + 1] == "a.png"
    assert args[args.index("--end-image") + 1] == "b.png"
    assert args.count("--image") == 2
    assert args[args.index("--duration") + 1] == "5"


def test_refs_none_skipped(monkeypatch):
    """refs=None должен просто пропускаться, без падения."""
    calls = patch_run(monkeypatch, stdout=json.dumps(["j-2"]))
    hf.submit("nano_banana_flash", {"prompt": "test", "refs": None})
    assert "--image" not in calls[0]


def test_nonzero_exit_raises(monkeypatch):
    patch_run(monkeypatch, returncode=1, stderr="quota exceeded")
    with pytest.raises(hf.HiggsfieldError, match="quota exceeded"):
        hf.poll("j-1")


def test_poll_returns_dict_on_success(monkeypatch):
    data = {"id": "j-1", "status": "completed", "result_url": "http://x/r.mp4"}
    patch_run(monkeypatch, stdout=json.dumps(data))
    result = hf.poll("j-1")
    assert result["status"] == "completed"


def test_poll_non_json_stdout_returns_raw(monkeypatch):
    """Нежурнальный stdout → {"raw": ...}."""
    patch_run(monkeypatch, stdout="not json")
    result = hf.poll("j-1")
    assert result == {"raw": "not json"}


def test_wait_polls_until_completed(monkeypatch):
    answers = [{"status": "in_progress"}, {"status": "completed", "result_url": "u"}]
    monkeypatch.setattr(hf, "poll", lambda j: answers.pop(0))
    monkeypatch.setattr(hf.time, "sleep", lambda s: None)
    assert hf.wait("j-1")["status"] == "completed"


def test_wait_timeout_raises(monkeypatch):
    """Если всегда in_progress — HiggsfieldError после timeout."""
    monkeypatch.setattr(hf, "poll", lambda j: {"status": "in_progress"})
    monkeypatch.setattr(hf.time, "sleep", lambda s: None)
    # timeout=0 → сразу истёк
    with pytest.raises(hf.HiggsfieldError, match="[Tt]imeout|timeout"):
        hf.wait("j-1", timeout_sec=0, interval_sec=1)


def test_download_fetches_result_url(monkeypatch, tmp_path):
    monkeypatch.setattr(hf, "poll", lambda j: {"status": "completed", "result_url": "http://x/r.png"})

    def fake_fetch(url, dest):
        from pathlib import Path
        Path(dest).write_bytes(b"data")

    monkeypatch.setattr(hf, "_fetch", fake_fetch)
    out = hf.download("j-1", tmp_path / "sub" / "out.png")
    assert out.exists()


def test_download_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(hf, "poll", lambda j: {"status": "completed", "result_url": "http://x/r.png"})
    monkeypatch.setattr(hf, "_fetch", lambda url, dest: None)  # «скачал», но файла нет
    with pytest.raises(hf.HiggsfieldError, match="missing"):
        hf.download("j-1", tmp_path / "out.png")


def test_download_incomplete_job_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(hf, "poll", lambda j: {"status": "in_progress", "result_url": ""})
    with pytest.raises(hf.HiggsfieldError):
        hf.download("j-1", tmp_path / "out.png")
