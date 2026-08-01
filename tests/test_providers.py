"""Тесты слоя провайдеров (scripts/factory/providers/).

Сеть полностью замокана: подменяем `_request` (HTTP JSON) и `_download_file`.
Живых запросов в CI нет (ТЗ §2).
"""
import pytest

from factory.providers import get_provider
from factory.providers.base import ProviderError
from factory.providers.wavespeed import WaveSpeedProvider
from factory.providers.runware import RunwareProvider
from factory.providers.openrouter import OpenRouterProvider

CARD = """---
id: seedance_2_0
type: video
status: verified
providers:
  wavespeed:
    pricing: scaled
    supports_start_end: true
    res_mult: {720p: 1.0, 1080p: 1.4}
    tiers:
      fast: { id: "bytedance/seedance-v2-fast/image-to-video", usd_per_sec: 0.10 }
    default_tier: fast
  runware:
    pricing: scaled
    supports_start_end: true
    res_mult: {720p: 1.0, 1080p: 2.25}
    tiers:
      fast: { id: "bytedance:seedance@2.0", usd_per_sec: 0.13 }
    default_tier: fast
  openrouter:
    pricing: scaled
    supports_start_end: true
    res_mult: {720p: 1.0, 1080p: 2.25}
    tiers:
      std: { id: "bytedance/seedance-2.0", usd_per_sec: 0.151 }
    default_tier: std
---
# Seedance 2.0
"""


@pytest.fixture
def kdir(tmp_path):
    d = tmp_path / "knowledge" / "video"
    d.mkdir(parents=True)
    (d / "seedance_2_0.md").write_text(CARD, encoding="utf-8")
    return tmp_path / "knowledge"


# Метаданные провайдеров для параметризации.
PROVIDERS = {
    "wavespeed": dict(cls=WaveSpeedProvider, env="WAVESPEED_API_KEY",
                      est720=0.50, est1080=0.70),
    "runware": dict(cls=RunwareProvider, env="RUNWARE_API_KEY",
                    est720=0.65, est1080=0.13 * 5 * 2.25),
    "openrouter": dict(cls=OpenRouterProvider, env="OPENROUTER_API_KEY",
                       est720=0.755, est1080=0.151 * 5 * 2.25),
}


def make(name, kdir):
    return PROVIDERS[name]["cls"](knowledge_dir=kdir)


# --- Фабрика ---

@pytest.mark.parametrize("name,cls", [("wavespeed", WaveSpeedProvider),
                                      ("runware", RunwareProvider),
                                      ("openrouter", OpenRouterProvider)])
def test_get_provider_returns_class(name, cls):
    assert isinstance(get_provider(name), cls)


def test_get_provider_unknown_raises():
    with pytest.raises(ProviderError, match="unknown provider"):
        get_provider("nope")


def test_get_provider_higgsfield_gone():
    """Higgsfield вырезан — не должен быть доступен как провайдер."""
    with pytest.raises(ProviderError):
        get_provider("higgsfield")


def test_provider_unit_is_dollars():
    assert get_provider("wavespeed").unit == "$"


# --- Смета (estimate через estimate_media_cost) ---

@pytest.mark.parametrize("name", list(PROVIDERS))
def test_estimate_720p(name, kdir):
    p = make(name, kdir)
    got = p.estimate("seedance_2_0", {"resolution": "720p", "duration": 5})
    assert got == pytest.approx(PROVIDERS[name]["est720"])


def test_estimate_1080p_wavespeed_x14(kdir):
    p = make("wavespeed", kdir)
    assert p.estimate("seedance_2_0", {"resolution": "1080p", "duration": 5}) == pytest.approx(0.70)


def test_estimate_1080p_runware_x225(kdir):
    p = make("runware", kdir)
    assert p.estimate("seedance_2_0", {"resolution": "1080p", "duration": 5}) == pytest.approx(0.13 * 5 * 2.25)


# --- Отсутствие ключа → ProviderError (без сети) ---

@pytest.mark.parametrize("name", list(PROVIDERS))
def test_missing_api_key_raises(name, kdir, monkeypatch):
    monkeypatch.delenv(PROVIDERS[name]["env"], raising=False)
    p = make(name, kdir)
    with pytest.raises(ProviderError, match=PROVIDERS[name]["env"]):
        p.submit("seedance_2_0", {"prompt": "x", "duration": 5,
                                  "start_frame": "http://x/a.png"})


# --- submit: эндпоинт/пейлоад/возврат id (мок _request) ---

def test_wavespeed_submit(kdir, monkeypatch):
    captured = {}

    def fake_request(method, url, json_body=None):
        captured.update(method=method, url=url, body=json_body)
        return {"code": 200, "data": {"id": "task-1", "status": "created"}}

    p = make("wavespeed", kdir)
    monkeypatch.setattr(p, "_request", fake_request)
    job = p.submit("seedance_2_0", {"prompt": "m", "duration": 5,
                                    "resolution": "720p",
                                    "start_frame": "http://x/a.png",
                                    "end_frame": "http://x/b.png"})
    assert job == "task-1"
    assert captured["method"] == "POST"
    assert captured["url"] == \
        "https://api.wavespeed.ai/api/v3/bytedance/seedance-v2-fast/image-to-video"
    assert captured["body"]["duration"] == 5


def test_runware_submit(kdir, monkeypatch):
    captured = {}

    def fake_request(method, url, json_body=None):
        captured.update(method=method, url=url, body=json_body)
        return {"data": [{"taskUUID": json_body[0]["taskUUID"]}]}

    p = make("runware", kdir)
    monkeypatch.setattr(p, "_request", fake_request)
    job = p.submit("seedance_2_0", {"prompt": "m", "duration": 5,
                                    "start_frame": "http://x/a.png"})
    assert captured["url"] == "https://api.runware.ai/v1"
    task = captured["body"][0]
    assert task["taskType"] == "videoInference"
    assert task["model"] == "bytedance:seedance@2.0"
    assert job == task["taskUUID"]


def test_openrouter_submit(kdir, monkeypatch):
    captured = {}

    def fake_request(method, url, json_body=None):
        captured.update(method=method, url=url, body=json_body)
        return {"id": "job-1", "polling_url": "/api/v1/videos/job-1", "status": "pending"}

    p = make("openrouter", kdir)
    monkeypatch.setattr(p, "_request", fake_request)
    job = p.submit("seedance_2_0", {"prompt": "m", "duration": 5,
                                    "resolution": "720p",
                                    "start_frame": "http://x/a.png"})
    assert job == "job-1"
    assert captured["url"] == "https://openrouter.ai/api/v1/videos"
    assert captured["body"]["model"] == "bytedance/seedance-2.0"
    fi = captured["body"]["frame_images"][0]
    assert fi["frame_type"] == "first_frame"


# --- poll/wait: цикл до терминального статуса ---

POLL = {
    "wavespeed": (
        {"data": {"status": "processing"}},
        {"data": {"status": "completed", "outputs": ["http://cdn/x.mp4"]}},
    ),
    "runware": (
        {"data": [{"taskUUID": "J"}]},
        {"data": [{"taskUUID": "J", "videoURL": "http://cdn/x.mp4"}]},
    ),
    "openrouter": (
        {"status": "processing"},
        {"status": "completed", "unsigned_urls": ["http://cdn/x.mp4"]},
    ),
}


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_wait_polls_until_terminal(name, kdir, monkeypatch):
    processing, completed = POLL[name]
    answers = [processing, completed]
    p = make(name, kdir)
    monkeypatch.setattr(p, "poll", lambda job_id: answers.pop(0))
    monkeypatch.setattr("factory.providers.base.time.sleep", lambda s: None)
    result = p.wait("J", timeout_sec=10, interval_sec=1)
    assert p._status(result) == "completed"


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_download_fetches_result_url(name, kdir, monkeypatch, tmp_path):
    _, completed = POLL[name]
    p = make(name, kdir)
    monkeypatch.setattr(p, "poll", lambda job_id: completed)

    def fake_download(url, dest):
        from pathlib import Path
        assert url == "http://cdn/x.mp4"
        Path(dest).write_bytes(b"video")

    monkeypatch.setattr(p, "_download_file", fake_download)
    out = p.download("J", tmp_path / "sub" / "out.mp4")
    assert out.exists()


@pytest.mark.parametrize("name", list(PROVIDERS))
def test_download_failed_status_raises(name, kdir, monkeypatch, tmp_path):
    p = make(name, kdir)
    failed = {"wavespeed": {"data": {"status": "failed", "error": "boom"}},
              "runware": {"errors": [{"message": "boom"}]},
              "openrouter": {"status": "failed", "error": "boom"}}[name]
    monkeypatch.setattr(p, "poll", lambda job_id: failed)
    with pytest.raises(ProviderError):
        p.download("J", tmp_path / "out.mp4")


# --- Хардненинг: атомарность/очистка/таймаут/медиа/тир (оффлайн) ---

def test_download_tmp_cleanup_on_error(kdir, monkeypatch, tmp_path):
    """Сбой во время скачивания → tmp-файл удалён, исключение проброшено."""
    p = make("wavespeed", kdir)
    dest = tmp_path / "out.mp4"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    monkeypatch.setattr(p, "poll",
                        lambda job_id: {"data": {"status": "completed",
                                                 "outputs": ["http://cdn/x.mp4"]}})

    def bad_download(url, dest_str):
        from pathlib import Path
        Path(dest_str).write_bytes(b"partial")
        raise OSError("connection reset")

    monkeypatch.setattr(p, "_download_file", bad_download)
    with pytest.raises(OSError, match="connection reset"):
        p.download("J", dest)
    assert not tmp.exists()
    assert not dest.exists()


def test_download_atomic_no_tmp_left(kdir, monkeypatch, tmp_path):
    p = make("openrouter", kdir)
    dest = tmp_path / "out.mp4"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    monkeypatch.setattr(p, "poll",
                        lambda job_id: {"status": "completed",
                                        "unsigned_urls": ["http://cdn/x.mp4"]})
    monkeypatch.setattr(p, "_download_file",
                        lambda url, d: __import__("pathlib").Path(d).write_bytes(b"v"))
    out = p.download("J", dest)
    assert out == dest and dest.exists() and not tmp.exists()


def test_wait_timeout_raises(kdir, monkeypatch):
    p = make("runware", kdir)
    monkeypatch.setattr(p, "poll", lambda job_id: {"data": [{"taskUUID": "J"}]})  # вечно processing
    monkeypatch.setattr("factory.providers.base.time.sleep", lambda s: None)
    with pytest.raises(ProviderError, match="timeout"):
        p.wait("J", timeout_sec=0, interval_sec=1)


def test_media_local_file_base64(kdir, tmp_path):
    """Локальный путь кодируется в data-URI; http-URL пропускается как есть."""
    p = make("wavespeed", kdir)
    img = tmp_path / "frame.png"
    img.write_bytes(b"\x89PNG\r\n")
    encoded = p._media(str(img))
    assert encoded.startswith("data:image/png;base64,")
    assert p._media("http://x/a.png") == "http://x/a.png"


FLAT_2TIER = """---
id: kling3_0
type: video
status: verified
providers:
  wavespeed:
    supports_start_end: true
    pricing: flat
    tiers:
      std: { id: "kwaivgi/kling-v3.0-std/start-end-to-video", usd_per_sec: 0.084 }
      pro: { id: "kwaivgi/kling-v3.0-pro/start-end-to-video", usd_per_sec: 0.168 }
    default_tier: std
---
# Kling 3.0
"""


def test_submit_tier_selects_provider_path(tmp_path, monkeypatch):
    """Явный tier выбирает свой model-path/id у провайдера."""
    d = tmp_path / "knowledge" / "video"
    d.mkdir(parents=True)
    (d / "kling3_0.md").write_text(FLAT_2TIER, encoding="utf-8")
    p = WaveSpeedProvider(knowledge_dir=tmp_path / "knowledge")
    captured = {}
    monkeypatch.setattr(p, "_request", lambda method, url, json_body=None:
                        captured.update(url=url) or {"data": {"id": "t1"}})
    p.submit("kling3_0", {"prompt": "m", "duration": 5, "tier": "pro",
                          "start_frame": "http://x/a.png"})
    assert captured["url"].endswith("kling-v3.0-pro/start-end-to-video")


# --- WaveSpeed: настраиваемые имена медиа-полей (v3 JSON) + multipart (v1) ---

WS_JSON_FIELDS = """---
id: vidu_q2t_ws
type: video
status: verified
providers:
  wavespeed:
    id: "vidu/start-end-to-video-q2-turbo"
    media: { start: start_frame, end: end_frame }
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.4}
    usd_per_sec: 0.021
---
# vidu q2t (v3 json variant)
"""

WS_MULTIPART = """---
id: vidu_q2t_mp
type: video
status: verified
providers:
  wavespeed:
    id: "vidu/turbo/start-end-to-video"
    api: v1_multipart
    media: { start: start_frame, end: end_frame }
    supports_start_end: true
    pricing: scaled
    res_mult: {720p: 1.0, 1080p: 1.4}
    usd_per_sec: 0.021
---
# vidu q2t (v1 multipart variant)
"""


def _ws(tmp_path, text, mid):
    d = tmp_path / "knowledge" / "video"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mid}.md").write_text(text, encoding="utf-8")
    return WaveSpeedProvider(knowledge_dir=tmp_path / "knowledge")


def test_wavespeed_json_custom_media_fields(tmp_path, monkeypatch):
    """media.{start,end} переопределяют имена полей кадров в v3 JSON."""
    p = _ws(tmp_path, WS_JSON_FIELDS, "vidu_q2t_ws")
    captured = {}
    monkeypatch.setattr(p, "_request", lambda method, url, json_body=None:
                        captured.update(url=url, body=json_body) or {"data": {"id": "t"}})
    p.submit("vidu_q2t_ws", {"prompt": "m", "duration": 5, "resolution": "720p",
                             "start_frame": "http://x/a.png", "end_frame": "http://x/b.png"})
    assert captured["url"].endswith("/api/v3/vidu/start-end-to-video-q2-turbo")
    assert captured["body"]["start_frame"] == "http://x/a.png"
    assert captured["body"]["end_frame"] == "http://x/b.png"
    assert "image" not in captured["body"] and "end_image" not in captured["body"]


def test_wavespeed_default_media_fields_unchanged(kdir, monkeypatch):
    """Без media-конфига — прежние image/end_image (обратная совместимость)."""
    p = make("wavespeed", kdir)
    captured = {}
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None:
                        captured.update(body=json_body) or {"data": {"id": "t"}})
    p.submit("seedance_2_0", {"prompt": "m", "duration": 5, "tier": "fast",
                              "start_frame": "http://x/a.png"})
    assert captured["body"]["image"] == "http://x/a.png"


def test_wavespeed_multipart_uploads_files(tmp_path, monkeypatch):
    """api: v1_multipart → файлы кадров загружаются как multipart на /api/v1/."""
    p = _ws(tmp_path, WS_MULTIPART, "vidu_q2t_mp")
    start = tmp_path / "a.png"; start.write_bytes(b"\x89PNGstart")
    end = tmp_path / "b.png"; end.write_bytes(b"\x89PNGend")
    captured = {}

    def fake_mp(url, fields, files):
        captured.update(url=url, fields=fields, files=files)
        return {"data": {"id": "mp-1"}}

    monkeypatch.setattr(p, "_post_multipart", fake_mp)
    job = p.submit("vidu_q2t_mp", {"prompt": "m", "duration": 5, "resolution": "720p",
                                   "start_frame": str(start), "end_frame": str(end)})
    assert job == "mp-1"
    assert captured["url"].endswith("/api/v1/vidu/turbo/start-end-to-video")
    assert set(captured["files"]) == {"start_frame", "end_frame"}
    assert captured["files"]["start_frame"][1] == b"\x89PNGstart"
    assert captured["fields"]["duration"] == "5"
    assert captured["fields"]["prompt"] == "m"


def test_wavespeed_multipart_requires_local_file(tmp_path, monkeypatch):
    """multipart с http-URL вместо локального файла → понятная ошибка."""
    p = _ws(tmp_path, WS_MULTIPART, "vidu_q2t_mp")
    monkeypatch.setattr(p, "_post_multipart", lambda *a, **k: {"data": {"id": "x"}})
    with pytest.raises(ProviderError, match="локальн"):
        p.submit("vidu_q2t_mp", {"prompt": "m", "duration": 5,
                                 "start_frame": "http://x/a.png"})


def test_wavespeed_encode_multipart_body():
    """Кодировщик multipart кладёт поля и файл с границей."""
    ct, body = WaveSpeedProvider._encode_multipart(
        {"duration": "5"}, {"start_frame": ("a.png", b"PNGDATA")})
    assert ct.startswith("multipart/form-data; boundary=")
    assert b'name="duration"' in body and b"5" in body
    assert b'name="start_frame"; filename="a.png"' in body
    assert b"PNGDATA" in body
    boundary = ct.split("boundary=")[1]
    assert body.rstrip().endswith(f"--{boundary}--".encode())


# --- Аудит 2026-06-16: добитые ветки base/wait/download/тир + OpenRouter image ---

def test_wait_unknown_nonempty_status_treated_terminal(kdir, monkeypatch):
    """Неизвестный непустой статус (не в _POLLING) трактуется как терминальный —
    wait возвращает результат, а не зацикливается до таймаута."""
    p = make("openrouter", kdir)
    monkeypatch.setattr(p, "poll", lambda job_id: {"status": "weird_unknown"})
    monkeypatch.setattr("factory.providers.base.time.sleep", lambda s: None)
    result = p.wait("J", timeout_sec=10, interval_sec=1)
    assert result == {"status": "weird_unknown"}


def test_download_empty_result_url_raises(kdir, monkeypatch, tmp_path):
    """Терминальный, но не FAILED статус без result_url → понятная ошибка."""
    p = make("openrouter", kdir)
    monkeypatch.setattr(p, "poll",
                        lambda job_id: {"status": "completed", "unsigned_urls": []})
    with pytest.raises(ProviderError, match="без результата"):
        p.download("J", tmp_path / "out.mp4")


def test_download_no_file_written_raises_and_cleans(kdir, monkeypatch, tmp_path):
    """Если сетевой шов ничего не создал — download падает и не оставляет .tmp."""
    p = make("openrouter", kdir)
    dest = tmp_path / "out.mp4"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    monkeypatch.setattr(p, "poll", lambda job_id:
                        {"status": "completed", "unsigned_urls": ["http://cdn/x.mp4"]})
    monkeypatch.setattr(p, "_download_file", lambda url, d: None)  # шов ничего не пишет
    with pytest.raises(OSError):
        p.download("J", dest)
    assert not tmp.exists() and not dest.exists()


OR_IMAGE_CARD = """---
id: some_image
type: image
status: verified
providers:
  openrouter:
    id: "x/img"
    usd_per_image: 0.01
---
# img
"""


def test_openrouter_rejects_image_generation(tmp_path):
    """OpenRouter — только видео: image-карточка → ProviderError ДО сети."""
    d = tmp_path / "knowledge" / "images"
    d.mkdir(parents=True)
    (d / "some_image.md").write_text(OR_IMAGE_CARD, encoding="utf-8")
    p = OpenRouterProvider(knowledge_dir=tmp_path / "knowledge")
    with pytest.raises(ProviderError, match="изображ"):
        p.submit("some_image", {"prompt": "x"})


def test_wavespeed_file_part_rejects_data_uri():
    """v1_multipart требует локальный файл — data-URI отвергается (как и http)."""
    with pytest.raises(ProviderError, match="локальн"):
        WaveSpeedProvider._file_part("data:image/png;base64,AAAA")


def test_estimate_1080p_openrouter_x225(kdir):
    """OpenRouter 1080p scaled = база720p × 2.25."""
    p = make("openrouter", kdir)
    assert p.estimate("seedance_2_0", {"resolution": "1080p", "duration": 5}) == \
        pytest.approx(0.151 * 5 * 2.25)


def test_submit_unknown_tier_raises(kdir):
    """Неизвестный tier валится в _concrete_id ДО сетевого вызова."""
    p = make("wavespeed", kdir)
    with pytest.raises(ProviderError, match="tier"):
        p.submit("seedance_2_0", {"prompt": "m", "duration": 5, "tier": "nonexistent",
                                  "start_frame": "http://x/a.png"})


def test_openrouter_download_sends_bearer(kdir, tmp_path, monkeypatch):
    """OpenRouter unsigned_urls (api/v1/videos/<id>/content) ТРЕБУЮТ Bearer —
    скачивание должно слать Authorization (иначе HTTP 401, выявлено на спайке)."""
    import urllib.request
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
    p = make("openrouter", kdir)
    captured = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"VIDEOBYTES"

    def fake_urlopen(req, timeout=None):
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "out.mp4"
    p._download_file("https://openrouter.ai/api/v1/videos/x/content?index=0", str(dest))
    assert captured["auth"] == "Bearer test-key-123"
    assert dest.read_bytes() == b"VIDEOBYTES"


# --- Спайк 2026-07-08: card-driven стиль разрешения WaveSpeed image-моделей ---
# Живые схемы /api/v3/models: flux/seedream/z_image принимают ТОЛЬКО size "W*H"
# (aspect_ratio/resolution молча игнорируются -> квадрат); nano-banana принимает
# aspect_ratio + resolution в k-нотации (0.5k/1k/2k/4k), "720p" -> HTTP 400.

WS_SIZE_STYLE = """---
id: flux_klein_test
type: image
status: verified
providers:
  wavespeed:
    id: "wavespeed-ai/flux-2-klein-9b/text-to-image"
    resolution_style: size
    pricing: flat
    usd_per_image: 0.01
---
# flux size-style
"""

WS_K_STYLE = """---
id: nano_test
type: image
status: verified
providers:
  wavespeed:
    id: "google/nano-banana-2/text-to-image"
    resolution_style: k
    pricing: flat
    usd_per_image: 0.07
---
# nano k-style
"""


def _ws_img(tmp_path, text, mid):
    d = tmp_path / "knowledge" / "images"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mid}.md").write_text(text, encoding="utf-8")
    return WaveSpeedProvider(knowledge_dir=tmp_path / "knowledge")


def _captured_submit(p, monkeypatch, model, params):
    captured = {}
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None:
                        captured.update(url=u, body=json_body) or {"data": {"id": "t"}})
    p.submit(model, params)
    return captured


@pytest.mark.parametrize("resolution,aspect,size", [
    ("720p", "16:9", "1280*720"),
    ("720p", "9:16", "720*1280"),
    ("1080p", "16:9", "1920*1080"),
    ("1080p", "9:16", "1080*1920"),
    ("720p", "1:1", "1024*1024"),
    ("1080p", "1:1", "2048*2048"),
])
def test_ws_size_style_maps_resolution_aspect(tmp_path, monkeypatch,
                                              resolution, aspect, size):
    p = _ws_img(tmp_path, WS_SIZE_STYLE, "flux_klein_test")
    c = _captured_submit(p, monkeypatch, "flux_klein_test",
                         {"prompt": "x", "resolution": resolution,
                          "aspect_ratio": aspect})
    assert c["body"]["size"] == size
    assert "aspect_ratio" not in c["body"] and "resolution" not in c["body"]


def test_ws_size_style_default_aspect_16x9(tmp_path, monkeypatch):
    p = _ws_img(tmp_path, WS_SIZE_STYLE, "flux_klein_test")
    c = _captured_submit(p, monkeypatch, "flux_klein_test",
                         {"prompt": "x", "resolution": "720p"})
    assert c["body"]["size"] == "1280*720"


def test_ws_size_style_unknown_combo_raises(tmp_path, monkeypatch):
    p = _ws_img(tmp_path, WS_SIZE_STYLE, "flux_klein_test")
    monkeypatch.setattr(p, "_request", lambda *a, **k: {"data": {"id": "t"}})
    with pytest.raises(ProviderError, match="resolution_style"):
        p.submit("flux_klein_test", {"prompt": "x", "resolution": "720p",
                                     "aspect_ratio": "21:9"})


def test_ws_k_style_maps_resolution(tmp_path, monkeypatch):
    p = _ws_img(tmp_path, WS_K_STYLE, "nano_test")
    c = _captured_submit(p, monkeypatch, "nano_test",
                         {"prompt": "x", "resolution": "720p",
                          "aspect_ratio": "16:9"})
    assert c["body"]["resolution"] == "1k"
    assert c["body"]["aspect_ratio"] == "16:9"


def test_ws_k_style_1080p_is_2k(tmp_path, monkeypatch):
    p = _ws_img(tmp_path, WS_K_STYLE, "nano_test")
    c = _captured_submit(p, monkeypatch, "nano_test",
                         {"prompt": "x", "resolution": "1080p"})
    assert c["body"]["resolution"] == "2k"


def test_ws_k_style_native_k_passthrough(tmp_path, monkeypatch):
    p = _ws_img(tmp_path, WS_K_STYLE, "nano_test")
    c = _captured_submit(p, monkeypatch, "nano_test",
                         {"prompt": "x", "resolution": "4k"})
    assert c["body"]["resolution"] == "4k"


def test_ws_no_style_passthrough_unchanged(kdir, monkeypatch):
    """Без resolution_style — прежнее поведение (видео-модели и пр.)."""
    p = make("wavespeed", kdir)
    captured = {}
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None:
                        captured.update(body=json_body) or {"data": {"id": "t"}})
    p.submit("seedance_2_0", {"prompt": "x", "duration": 5, "tier": "fast",
                              "resolution": "720p", "aspect_ratio": "16:9",
                              "start_frame": "http://x/a.png"})
    assert captured["body"]["resolution"] == "720p"
    assert captured["body"]["aspect_ratio"] == "16:9"


WS_OMIT_STYLE = """---
id: kling_test
type: video
status: verified
providers:
  wavespeed:
    id: "kwaivgi/kling-v3.0-std/image-to-video"
    resolution_style: omit
    supports_start_end: true
    pricing: flat
    usd_per_sec: 0.084
---
# kling omit-style
"""


def test_ws_omit_style_drops_resolution_and_aspect(tmp_path, monkeypatch):
    """kling: схема БЕЗ resolution/aspect_ratio — конвейер шлёт их всегда,
    resolution_style: omit выбрасывает оба до сети."""
    d = tmp_path / "knowledge" / "video"
    d.mkdir(parents=True)
    (d / "kling_test.md").write_text(WS_OMIT_STYLE, encoding="utf-8")
    p = WaveSpeedProvider(knowledge_dir=tmp_path / "knowledge")
    captured = {}
    monkeypatch.setattr(p, "_request", lambda m, u, json_body=None:
                        captured.update(body=json_body) or {"data": {"id": "t"}})
    p.submit("kling_test", {"prompt": "x", "duration": 5, "resolution": "720p",
                            "aspect_ratio": "16:9", "start_frame": "http://x/a.png"})
    assert "resolution" not in captured["body"]
    assert "aspect_ratio" not in captured["body"]
    assert captured["body"]["duration"] == 5
