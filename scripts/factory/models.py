"""Карточки моделей: YAML-frontmatter с матрицей возможностей (спека §6)."""
from __future__ import annotations

from pathlib import Path

from factory.artifact import ArtifactError, split_frontmatter


class ModelError(ValueError):
    pass


# Каталоги, в которых лежат карточки моделей. Остальное в knowledge/ —
# контракты провайдеров (`*-api.md`), карточки жанров и шаблон.
MODEL_DIRS = ("images", "video", "audio")


def load_card(path: Path) -> dict:
    """Прочитать матрицу возможностей карточки модели.

    Разбор frontmatter общий с factory.artifact (построчный поиск разделителя,
    см. split_frontmatter) — иначе значение с '---' внутри (например
    комментарий-разделитель шаблона карточки) молча обрезает frontmatter.
    Тело карточки отбрасывается: значима только матрица возможностей.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        card, _body = split_frontmatter(text, path)
    except ArtifactError as e:
        raise ModelError(str(e)) from None
    for req in ("id", "type", "status"):
        if req not in card:
            raise ModelError(f"{path}: frontmatter missing {req!r}")
    return card


def all_cards(knowledge_dir: Path) -> list[dict]:
    """Все карточки моделей, какие есть. Битые пропускаются молча.

    Нужна панели: чтобы предложить человеку выбор модели по роли, надо знать
    весь список, а не искать по одному имени. Пропуск битой карточки — то же
    решение, что в `find_card`: одна сломанная не должна прятать остальные.
    """
    cards = []
    for path in sorted(Path(knowledge_dir).rglob("*.md")):
        if path.name.startswith("_") or path.parent.name not in MODEL_DIRS:
            continue
        try:
            cards.append(load_card(path))
        except ModelError:
            continue
    return cards


def find_card(knowledge_dir: Path, model_id: str) -> dict:
    """Битые карточки пропускаются (не должны ломать поиск остальных);
    если модель не найдена — пропущенные перечисляются в ошибке."""
    skipped: list[str] = []
    for p in sorted(Path(knowledge_dir).rglob("*.md")):
        if p.name.startswith("_"):
            continue
        # Карточки моделей лежат по типам; всё прочее в knowledge/ — контракты
        # провайдеров и карточки жанров, они моделями не притворяются. Без этой
        # проверки они попадали в список «битых карточек» в сообщении об ошибке
        # и путали того, кто его читает.
        if p.parent.name not in MODEL_DIRS:
            continue
        try:
            card = load_card(p)
        except ModelError:
            skipped.append(str(p))
            continue
        if card["id"] == model_id:
            return card
    msg = f"no knowledge card for model {model_id!r}"
    if skipped:
        msg += f" (skipped malformed cards: {', '.join(skipped)})"
    raise ModelError(msg)


# Статусы карточки и их смысл для гейта трат.
#
# skeleton — возможности и цена не подтверждены ничем: трата запрещена.
# catalog  — пути и цены взяты из КАТАЛОГА провайдера, живой генерации не было;
#            трата разрешена осознанным решением человека (2026-09-04, veo).
#            Каталог уже дважды ошибался на аудио — у gemini в 2.4 раза, у qwen3
#            вдвое, — поэтому первая же реальная генерация обязана сверить цену
#            списанием и перевести карточку в verified с замеренным числом.
# verified — подтверждено живой генерацией: и путь, и цена.
CARD_STATUSES = {"skeleton", "catalog", "verified"}
_BLOCKING_STATUSES = {"skeleton"}


def _status_problems(card: dict) -> list[str]:
    """Проверка статуса карточки — одна на все три валидатора.

    Неизвестный статус (опечатка) НЕ должен молча открывать трату: раньше код
    сравнивал только со строкой "skeleton", и `status: verifed` проходил гейт.
    """
    status = card.get("status")
    if status not in CARD_STATUSES:
        return [f"{card['id']}: unknown status {status!r} "
                f"(allowed: {sorted(CARD_STATUSES)})"]
    if status in _BLOCKING_STATUSES:
        return [f"{card['id']}: card is a skeleton — capabilities not verified, "
                "verify before spending credits"]
    return []


def validate_video_model(card: dict, segment_seconds: int,
                         provider: str | None = None,
                         needs_end_frame: bool = False) -> list[str]:
    """Спека §6: валидация выбора модели ДО траты денег.

    Если задан ``provider`` И в карте есть блок ``providers`` — проверяем
    возможности (end-кадр, сетку длительностей) ПОД ВЫБРАННОГО провайдера.
    Без ``provider`` (или если в карте нет ``providers``) — legacy-поведение
    по top-level полям карточки.

    ``needs_end_frame`` — есть ли в ПЛАНЕ хоть один отрезок со стыком кадров.
    Спрашивается у плана, а не у модели, потому что `end_frame` необязателен с
    2026-09-03: отрезок живёт внутри одного плана, стык делает монтаж. Пока
    поддержка end-кадра требовалась всегда, гейт отказывал моделям, которые
    делают ровно ту работу, какую конвейер им и даёт (grok, hailuo, kling-std),
    — то есть защищал от схемы, от которой сам конвейер уже отказался. Панель
    плана не знает и спрашивает без него: там вопрос «можно ли выбрать», а
    несовместимость со стыком всплывёт гейтом платной стадии, до траты.
    """
    problems: list[str] = []
    if card["type"] != "video":
        problems.append(f"{card['id']}: not a video model")
        return problems

    providers = card.get("providers")
    if provider is not None and providers is not None:
        pv = providers.get(provider)
        if pv is None:
            problems.append(
                f"{card['id']}: not available on provider {provider!r} "
                f"(declared: {sorted(providers)})")
            return problems
        supports = pv.get("supports_start_end")
        allowed = pv.get("allowed_durations", card.get("allowed_durations"))
        max_clip = pv.get("max_clip_seconds")  # None → сетка неизвестна, не проверяем
    else:
        supports = card.get("supports_start_end_frame")
        allowed = card.get("allowed_durations")
        max_clip = card.get("max_clip_seconds", 0)

    if needs_end_frame and not supports:
        problems.append(
            f"{card['id']}: no end frame support on provider {provider!r} — "
            "в плане есть отрезки со стыком кадров (end_frame)")
    if max_clip is not None and max_clip < segment_seconds:
        problems.append(
            f"{card['id']}: max clip {max_clip}s "
            f"< required {segment_seconds}s")
    # Проверяем сетку допустимых длительностей: None/[] = сетка неизвестна, не проверяем
    if allowed and segment_seconds not in allowed:
        problems.append(
            f"{card['id']}: duration {segment_seconds}s not in allowed grid {allowed}")
    problems += _status_problems(card)
    return problems


def validate_image_model(card: dict, provider: str | None = None,
                         needs_refs: bool = False) -> list[str]:
    """Гейт трат для раскадровки (image), симметрично ``validate_video_model``.

    Картинкам не нужны start/end-сцепка и сетка длительностей — проверяем тип,
    доступность под выбранного провайдера (если задан И в карте есть ``providers``)
    и статус ``skeleton`` (маппинг провайдера не подтверждён живьём → не тратить).

    ``needs_refs`` — есть ли в ПЛАНЕ кадр с референсами. Вопрос задаётся плану,
    как и про end-кадр у видео: модель без входных картинок (grok-imagine
    text-to-image) годится для фона и предмета, но не для лица сериала, и
    выяснить это нужно ДО сметы, а не отказом провайдера на середине батча.
    Поле ``supports_refs`` необязательно: не объявлено — считаем, что принимает.
    """
    problems: list[str] = []
    if card["type"] != "image":
        problems.append(f"{card['id']}: not an image model")
        return problems

    if needs_refs and card.get("supports_refs") is False:
        problems.append(
            f"{card['id']}: не принимает референсы, а в плане есть кадры с refs")

    providers = card.get("providers")
    if provider is not None and providers is not None:
        if providers.get(provider) is None:
            problems.append(
                f"{card['id']}: not available on provider {provider!r} "
                f"(declared: {sorted(providers)})")
            return problems

    problems += _status_problems(card)
    return problems


def estimate_media_cost(card: dict, provider: str, resolution: str,
                        duration_sec: float, tier: str | None = None) -> float:
    """Смета в долларах под провайдера/разрешение/тип цены (ТЗ §6, FINAL §3).

    Источник цен — frontmatter карточки (блок ``providers``):
    - image / ``usd_per_image`` → плоская цена за изображение (разрешение/длительность
      не влияют);
    - video ``pricing: flat`` → ``usd_per_sec × duration_sec`` (от разрешения не зависит);
    - video ``pricing: scaled`` → ``usd_per_sec(720p) × duration_sec × res_mult[resolution]``.
      Множитель разрешения задаётся В КАРТОЧКЕ и у каждой модели свой: единого
      «×1.4 у WaveSpeed» нет — живые пробы 2026-08-01 дали 2.5 у seedance_2_0 и
      2.0 у seedance1_5 на том же провайдере. Источник — формула из каталога
      провайдера, не общее правило.

    Тир (``fast``/``std``/``pro``) выбирает запись из ``providers[p].tiers``;
    по умолчанию — ``default_tier``.
    """
    providers = card.get("providers") or {}
    pv = providers.get(provider)
    if pv is None:
        raise ModelError(
            f"{card.get('id')}: no pricing for provider {provider!r} "
            f"(declared: {sorted(providers)})")

    entry = pv
    if "tiers" in pv:
        chosen = tier or pv.get("default_tier")
        if chosen not in pv["tiers"]:
            raise ModelError(
                f"{card.get('id')}: unknown tier {chosen!r} for provider {provider!r} "
                f"(declared: {sorted(pv['tiers'])})")
        entry = pv["tiers"][chosen]

    usd_per_image = entry.get("usd_per_image", pv.get("usd_per_image"))
    if usd_per_image is not None or card.get("type") == "image":
        if usd_per_image is None:
            raise ModelError(f"{card.get('id')}: no usd_per_image for provider {provider!r}")
        return float(usd_per_image)

    usd_per_sec = entry.get("usd_per_sec", pv.get("usd_per_sec"))
    if usd_per_sec is None:
        raise ModelError(f"{card.get('id')}: no usd_per_sec for provider {provider!r}")
    cost = float(usd_per_sec) * float(duration_sec)

    if pv.get("pricing") == "scaled":
        res_mult = pv.get("res_mult", {})
        if resolution not in res_mult:
            raise ModelError(
                f"{card.get('id')}: no res_mult for resolution {resolution!r} "
                f"on provider {provider!r}")
        cost *= float(res_mult[resolution])
    return cost


def duration_problem(card: dict, provider: str | None,
                     seconds: float) -> str | None:
    """Влезает ли столько секунд в ОДИН вызов модели. None — влезает.

    Предел объявляется ДАННЫМИ (`max_duration_sec` у провайдера или у карточки);
    не объявлен — не проверяем, та же дисциплина, что у `allowed_durations`:
    выдуманный предел отказывал бы в работе, которую модель делает.

    Нужно потому, что провайдер отбивает такое уже ПОСЛЕ сметы: WaveSpeed вернул
    «field "duration" must be at most 360, got number 380» на музыку в 380 с,
    когда план был утверждён и смета посчитана (живой прогон 2026-09-11). Это
    гейт трат, а не сюрприз по факту запроса.
    """
    entry = (card.get("providers") or {}).get(provider) or {}
    limit = entry.get("max_duration_sec", card.get("max_duration_sec"))
    if limit is None or seconds <= float(limit):
        return None
    return (f"{card.get('id')}: длительность {seconds:g} с больше предела "
            f"модели {float(limit):g} с за один вызов")


def validate_audio_model(card: dict, provider: str | None = None,
                         audio_kind: str | None = None) -> list[str]:
    """Валидация аудио-модели ДО траты кредитов (спека фазы 2 §5).

    Симметрична validate_image_model: кроме типа и `status`, проверяет, что
    модель объявлена У ВЫБРАННОГО провайдера. Гейт трат карточного уровня
    (`status: skeleton`) на провайдера не смотрит, поэтому карточка, открытая
    живой пробой на одном провайдере, без этой проверки открывала бы трату и на
    другом, где id и цена не подтверждены.

    `audio_kind` — роль (tts/sfx/music/foley/lipsync): защищает от подстановки
    музыкальной модели в роль озвучки, где ошибка вскрылась бы только на слух.
    """
    problems: list[str] = []
    if card["type"] != "audio":
        problems.append(f"{card['id']}: not an audio model")
    problems += _status_problems(card)
    if audio_kind and card.get("audio_kind") != audio_kind:
        problems.append(
            f"{card['id']}: audio_kind is {card.get('audio_kind')!r}, "
            f"role needs {audio_kind!r}")
    if provider is not None:
        providers = card.get("providers") or {}
        if provider not in providers:
            problems.append(
                f"{card['id']}: not available on provider {provider!r} "
                f"(declared: {sorted(providers)})")
    return problems
