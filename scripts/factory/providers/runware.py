"""Адаптер Runware (REST). Контракт — knowledge/runware-api.md.

Единый эндпоинт POST api.runware.ai/v1 принимает массив задач. submit →
videoInference/imageInference с taskUUID; poll → getResponse по тому же taskUUID.
Результат — videoURL/imageURL. AIR-id модели и имена полей живут здесь и в доке.
"""
from __future__ import annotations

import uuid

from factory.providers.base import BaseHTTPProvider, ProviderError

_ENDPOINT = "https://api.runware.ai/v1"


class RunwareError(ProviderError):
    """Ошибка Runware."""


class RunwareProvider(BaseHTTPProvider):
    name = "runware"
    api_key_env = "RUNWARE_API_KEY"

    def submit(self, model: str, params: dict) -> str:
        card = self._card(model)
        air = self._concrete_id(card, params.get("tier"))  # напр. bytedance:seedance@2.0
        is_image = card.get("type") == "image"
        task_uuid = str(uuid.uuid4())
        task: dict = {
            "taskType": "imageInference" if is_image else "videoInference",
            "taskUUID": task_uuid,
            "model": air,
            "positivePrompt": params.get("prompt", ""),
            "includeCost": True,
        }
        if not is_image and params.get("duration") is not None:
            task["duration"] = params["duration"]
        if params.get("resolution"):
            task["resolution"] = params["resolution"]

        frames = []
        if params.get("start_frame"):
            frames.append({"image": self._media(params["start_frame"]), "frame": "first"})
        if params.get("end_frame"):
            frames.append({"image": self._media(params["end_frame"]), "frame": "last"})
        refs = params.get("refs") or []
        if frames or refs:
            task["inputs"] = {}
            if frames:
                task["inputs"]["frameImages"] = frames
            if refs:
                task["inputs"]["referenceImages"] = [self._media(r) for r in refs]

        resp = self._request("POST", _ENDPOINT, json_body=[task])
        if resp.get("errors"):
            raise RunwareError(f"submit errors: {resp['errors']!r}")
        return task_uuid

    def poll(self, job_id: str) -> dict:
        return self._request("POST", _ENDPOINT,
                             json_body=[{"taskType": "getResponse", "taskUUID": job_id}])

    def _item(self, result: dict) -> dict | None:
        data = result.get("data") or []
        return data[0] if data else None

    def _status(self, result: dict) -> str:
        if result.get("errors"):
            return "failed"
        item = self._item(result)
        if item is None:
            return ""
        if item.get("videoURL") or item.get("imageURL"):
            return "completed"
        return item.get("status", "")

    def _result_url(self, result: dict) -> str:
        item = self._item(result) or {}
        return item.get("videoURL") or item.get("imageURL") or ""
