"""Адаптер Runware (REST). Контракт — knowledge/runware-api.md.

Единый эндпоинт POST api.runware.ai/v1 принимает массив задач. submit →
videoInference/imageInference с taskUUID; poll → getResponse по тому же taskUUID.
Результат — videoURL/imageURL. AIR-id модели и имена полей живут здесь и в доке.
"""
from __future__ import annotations

import uuid

from factory.providers.base import BaseHTTPProvider, ProviderError

_ENDPOINT = "https://api.runware.ai/v1"

# Runware отклоняет строку resolution ("720p") — imageInference/videoInference хотят
# целочисленные width/height. Подтверждено живьём 2026-08-01: imageInference для
# flux_2_klein упал HTTP 400 missingDimensionParameters ДО создания задачи, $0
# списано (knowledge/runware-api.md, «Спайк 2026-08-01»). Таблица — 16:9-база;
# 9:16 получаем перестановкой сторон в submit().
#
# 720p = 1280x720: оба кратны 16 — FLUX.2 [klein] 9B (наш imageInference,
# runware:400@2) требует width/height в диапазоне 128-2048 с шагом 16
# (runware.ai/docs/models/bfl-flux-2-klein-9b.md, context7 2026-08-01); те же
# 1280x720 — рабочий пример в доке Vidu Q2 Turbo (наш videoInference, vidu:3@2;
# runware.ai/docs/models/vidu-q2-turbo/examples). Одна пара размеров закрывает
# обе задачи этой карточки.
#
# 1080p сюда намеренно НЕ включён: для FLUX 2 Klein 9B высота 1080 не кратна 16
# (1080/16 = 67.5) — валидного round-числа без искажения соотношения сторон нет,
# а видео-модели (Vidu) такого ограничения в доках не декларируют вовсе — единой
# пары размеров для обоих типов задач без отдельной живой проверки нет. Гадать
# нечестно (см. правило проекта): пока resolution не в таблице — submit падает
# явной ошибкой ниже, а не шлёт непроверенные px.
_RESOLUTIONS = {
    "720p": (1280, 720),
}


class RunwareError(ProviderError):
    """Ошибка Runware."""


class RunwareProvider(BaseHTTPProvider):
    name = "runware"
    api_key_env = "RUNWARE_API_KEY"

    def preflight_problems(self, model: str, params: dict) -> list[str]:
        """Разрешение вне _RESOLUTIONS ловим ДО сметы, а не в submit — иначе
        пользователь видит подтверждённую цену и весь батч падает в fail
        (ревью-находка: смета не должна обещать то, что submit не выполнит)."""
        resolution = params.get("resolution")
        if resolution and resolution not in _RESOLUTIONS:
            return [f"Runware: неизвестное resolution {resolution!r}; "
                    f"замаплены только {sorted(_RESOLUTIONS)}"]
        return []

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
            # Без этого imageInference отдаёт результат ПРЯМО в ответе на сабмит
            # (deliveryMethod по умолчанию sync для image, async для video), и
            # наш submit→poll→download цикл поллит getResponse по уже закрытой
            # задаче до таймаута. Просим async явно — одна ветка на оба типа.
            # Подтверждено живьём 2026-08-01, см. knowledge/runware-api.md.
            "deliveryMethod": "async",
        }
        if not is_image and params.get("duration") is not None:
            task["duration"] = params["duration"]
        if params.get("resolution"):
            dims = _RESOLUTIONS.get(params["resolution"])
            if dims is None:
                raise RunwareError(
                    f"неизвестное resolution {params['resolution']!r} для Runware; "
                    f"замаплены только {sorted(_RESOLUTIONS)}")
            width, height = dims
            if params.get("aspect_ratio") == "9:16":
                width, height = height, width
            task["width"] = width
            task["height"] = height

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
