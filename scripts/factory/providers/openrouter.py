"""Адаптер OpenRouter (REST, только видео). Контракт — knowledge/openrouter-api.md.

POST api/v1/videos (submit) → {id, polling_url, status}; GET api/v1/videos/<id>
(poll) → {status, unsigned_urls[]}. frame_images задают первый/последний кадр.
Vidu и генерация изображений на OpenRouter не поддерживаются (FINAL §1).
"""
from __future__ import annotations

from factory.providers.base import BaseHTTPProvider, ProviderError

_BASE = "https://openrouter.ai/api/v1/videos"


class OpenRouterError(ProviderError):
    """Ошибка OpenRouter."""


class OpenRouterProvider(BaseHTTPProvider):
    name = "openrouter"
    api_key_env = "OPENROUTER_API_KEY"

    def submit(self, model: str, params: dict) -> str:
        card = self._card(model)
        if card.get("type") == "image":
            raise OpenRouterError(
                "openrouter: генерация изображений не поддерживается (только видео)")
        air = self._concrete_id(card, params.get("tier"))  # напр. google/veo-3.1
        body: dict = {"model": air, "prompt": params.get("prompt", ""),
                      "generate_audio": False}
        if params.get("duration") is not None:
            body["duration"] = params["duration"]
        if params.get("resolution"):
            body["resolution"] = params["resolution"]
        if params.get("aspect_ratio"):
            body["aspect_ratio"] = params["aspect_ratio"]
        frames = []
        if params.get("start_frame"):
            frames.append(self._frame(params["start_frame"], "first_frame"))
        if params.get("end_frame"):
            frames.append(self._frame(params["end_frame"], "last_frame"))
        if frames:
            body["frame_images"] = frames
        refs = params.get("refs") or []
        if refs:
            body["input_references"] = [
                {"type": "image_url", "image_url": {"url": self._media(r)}} for r in refs]

        resp = self._request("POST", _BASE, json_body=body)
        job_id = resp.get("id")
        if not job_id:
            raise OpenRouterError(f"submit без id: {resp!r}")
        return str(job_id)

    @staticmethod
    def _frame(value: str, frame_type: str) -> dict:
        return {"type": "image_url",
                "image_url": {"url": BaseHTTPProvider._media(value)},
                "frame_type": frame_type}

    def poll(self, job_id: str) -> dict:
        return self._request("GET", f"{_BASE}/{job_id}")

    def _status(self, result: dict) -> str:
        return result.get("status", "")

    def _result_url(self, result: dict) -> str:
        urls = result.get("unsigned_urls") or []
        return urls[0] if urls else ""
