"""Адаптер WaveSpeed (REST). Контракт — knowledge/wavespeed-api.md.

Два стиля API, выбираются в карточке (`providers.wavespeed`):
- **v3 JSON** (по умолчанию): POST api/v3/<path>, кадры — поля изображения в JSON
  (URL/data-URI). Имена полей старт/энд настраиваются `media: {start, end}`
  (дефолт `image`/`end_image`).
- **v1 multipart** (`api: v1_multipart`): POST api/v1/<path> с загрузкой файлов кадров
  (multipart/form-data). Нужно для моделей вроде Vidu Q2 Turbo start-end-to-video.

poll/result — общий: GET api/v3/predictions/<id>/result → data.status + data.outputs[].
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from factory.providers.base import BaseHTTPProvider, ProviderError

_API = "https://api.wavespeed.ai/api/v3"
_API_V1 = "https://api.wavespeed.ai/api/v1"


class WaveSpeedError(ProviderError):
    """Ошибка WaveSpeed."""


class WaveSpeedProvider(BaseHTTPProvider):
    name = "wavespeed"
    api_key_env = "WAVESPEED_API_KEY"

    def submit(self, model: str, params: dict) -> str:
        card = self._card(model)
        pv = self._pv(card)
        path = self._concrete_id(card, params.get("tier"))
        media = pv.get("media") or {}
        start_field = media.get("start", "image")
        end_field = media.get("end", "end_image")

        if pv.get("api") == "v1_multipart":
            return self._submit_multipart(path, params, start_field, end_field)

        body = self._payload(card, params, start_field, end_field)
        self._apply_resolution_style(pv, body)
        resp = self._request("POST", f"{_API}/{path}", json_body=body)
        job_id = (resp.get("data") or {}).get("id")
        if not job_id:
            raise WaveSpeedError(f"submit без data.id: {resp!r}")
        return str(job_id)

    def poll(self, job_id: str) -> dict:
        return self._request("GET", f"{_API}/predictions/{job_id}/result")

    # Стили разрешения (живые схемы /api/v3/models, 2026-07-08):
    # size-модели (flux/seedream/z_image) знают только size "W*H" — aspect_ratio и
    # resolution молча игнорируются (получается квадрат по умолчанию);
    # k-модели (nano-banana) хотят resolution в k-нотации, "720p" -> HTTP 400;
    # omit-модели (kling) вообще без resolution/aspect_ratio в схеме — выбрасываем.
    _SIZE_TABLE = {
        ("720p", "16:9"): "1280*720", ("720p", "9:16"): "720*1280",
        ("720p", "1:1"): "1024*1024",
        ("1080p", "16:9"): "1920*1080", ("1080p", "9:16"): "1080*1920",
        ("1080p", "1:1"): "2048*2048",
    }
    _K_TABLE = {"720p": "1k", "1080p": "2k"}
    _K_NATIVE = {"0.5k", "1k", "2k", "4k"}

    def _apply_resolution_style(self, pv: dict, body: dict) -> None:
        style = pv.get("resolution_style")
        if not style:
            return
        resolution = body.pop("resolution", None)
        if style == "omit":
            body.pop("aspect_ratio", None)
        elif style == "size":
            aspect = body.pop("aspect_ratio", None) or "16:9"
            size = self._SIZE_TABLE.get((resolution, aspect))
            if not size:
                raise WaveSpeedError(
                    f"resolution_style=size: нет маппинга для "
                    f"({resolution!r}, {aspect!r}); известны {sorted(self._SIZE_TABLE)}")
            body["size"] = size
        elif style == "k":
            if resolution in self._K_NATIVE:
                body["resolution"] = resolution
            elif resolution in self._K_TABLE:
                body["resolution"] = self._K_TABLE[resolution]
            elif resolution is not None:
                raise WaveSpeedError(
                    f"resolution_style=k: неизвестное разрешение {resolution!r}; "
                    f"жду {sorted(self._K_NATIVE | set(self._K_TABLE))}")
        else:
            raise WaveSpeedError(
                f"неизвестный resolution_style {style!r} (знаю: size, k, omit)")

    # ---- v3 JSON ----
    def _payload(self, card: dict, params: dict,
                 start_field: str = "image", end_field: str = "end_image") -> dict:
        body: dict = {"prompt": params.get("prompt", "")}
        if params.get("aspect_ratio"):
            body["aspect_ratio"] = params["aspect_ratio"]
        if params.get("duration") is not None:
            body["duration"] = params["duration"]
        if params.get("resolution"):
            body["resolution"] = params["resolution"]
        if card.get("type") == "image":
            refs = params.get("refs") or []
            if refs:
                body["images"] = [self._media(r) for r in refs]
        else:
            if params.get("start_frame"):
                body[start_field] = self._media(params["start_frame"])
            if params.get("end_frame"):
                body[end_field] = self._media(params["end_frame"])
        return body

    # ---- v1 multipart (загрузка файлов кадров) ----
    def _submit_multipart(self, path: str, params: dict,
                          start_field: str, end_field: str) -> str:
        fields = {"prompt": params.get("prompt", "")}
        for k in ("duration", "resolution", "aspect_ratio", "movement_amplitude", "seed"):
            if params.get(k) is not None:
                fields[k] = str(params[k])
        files = {}
        if params.get("start_frame"):
            files[start_field] = self._file_part(params["start_frame"])
        if params.get("end_frame"):
            files[end_field] = self._file_part(params["end_frame"])
        resp = self._post_multipart(f"{_API_V1}/{path}", fields, files)
        job_id = (resp.get("data") or {}).get("id")
        if not job_id:
            raise WaveSpeedError(f"multipart submit без data.id: {resp!r}")
        return str(job_id)

    @staticmethod
    def _file_part(value: str) -> tuple[str, bytes]:
        if value.startswith(("http://", "https://", "data:")):
            raise WaveSpeedError(
                f"v1_multipart требует локальный файл кадра, получено: {value!r}")
        p = Path(value)
        return (p.name, p.read_bytes())

    @staticmethod
    def _encode_multipart(fields: dict, files: dict) -> tuple[str, bytes]:
        boundary = "----wsb" + uuid.uuid4().hex
        out = bytearray()
        for k, v in fields.items():
            out += (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                    ).encode("utf-8")
        for k, (filename, content) in files.items():
            out += (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'
                    "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
            out += bytes(content) + b"\r\n"
        out += f"--{boundary}--\r\n".encode("utf-8")
        return f"multipart/form-data; boundary={boundary}", bytes(out)

    def _post_multipart(self, url: str, fields: dict, files: dict) -> dict:
        content_type, body = self._encode_multipart(fields, files)
        headers = {"Authorization": f"Bearer {self._key()}",
                   "Content-Type": content_type}
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            b = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
            raise ProviderError(f"{self.name}: HTTP {e.code} на {url}: {b}") from None
        except urllib.error.URLError as e:
            raise ProviderError(
                f"{self.name}: сетевая ошибка на {url}: {e.reason}") from None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    # ---- общий результат ----
    def _status(self, result: dict) -> str:
        return (result.get("data") or {}).get("status", "")

    def _result_url(self, result: dict) -> str:
        outs = (result.get("data") or {}).get("outputs") or []
        return outs[0] if outs else ""
