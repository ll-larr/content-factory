"""Tavily — поиск в вебе для проверки фактов. Контракт: knowledge/tavily-api.md.

Зачем отдельный провайдер: познавательный жанр объявляет `fact_check: required`,
а правило проверяющего — не верить источнику автора и искать самостоятельно.
Движок Claude Code ищет своими инструментами, движку «модель по ключу» искать
нечем. Без этого ключа и без Claude Code познавательный жанр недоступен:
сочинённый факт дороже несделанного ролика.

Точные эндпоинт, имена полей и значения параметров живут ТОЛЬКО здесь и в
knowledge-доке (правило изоляции провайдера).
"""
from __future__ import annotations

from factory.providers.base import BaseSearchProvider, ProviderError

SEARCH_URL = "https://api.tavily.com/search"

# advanced стоит 2 кредита вместо 1 ($0.016 против $0.008), но отдаёт выдержки
# глубже одного абзаца. Проверка факта по заголовку — не проверка, а на фоне
# съёмки отрезка эта разница неразличима.
SEARCH_DEPTH = "advanced"

# Правило жанра требует пяти НЕЗАВИСИМЫХ источников. Восемь результатов дают
# запас на то, что часть из них окажется пересказами одной новости — а пять
# пересказов, по карточке жанра, это один источник, а не пять.
DEFAULT_MAX_RESULTS = 8


class TavilyProvider(BaseSearchProvider):
    name = "tavily"
    api_key_env = "TAVILY_API_KEY"

    def search(self, query: str, *, max_results: int = DEFAULT_MAX_RESULTS
               ) -> list[dict]:
        """Найденное по запросу: title, url, snippet, score.

        Пустой запрос отбиваем до сети: платить кредит за запрос, который нечего
        искать, незачем, а Tavily на него ответит ошибкой не о том.
        """
        query = (query or "").strip()
        if not query:
            raise ProviderError(f"{self.name}: пустой поисковый запрос")

        data = self._request("POST", SEARCH_URL, json_body={
            "query": query,
            "search_depth": SEARCH_DEPTH,
            "max_results": max(1, min(int(max_results), 20)),
            # Ответ, сочинённый моделью Tavily, — ещё один пересказ. Проверяющий
            # обязан смотреть на источники сам, иначе «пять источников»
            # превращаются в одно чужое мнение.
            "include_answer": False,
            # Полные страницы раздувают промпт в десятки раз; для сверки факта
            # достаточно выдержки.
            "include_raw_content": False,
        })

        results = data.get("results")
        if not isinstance(results, list):
            raise ProviderError(
                f"{self.name}: в ответе нет списка results: {data}")

        found = []
        for item in results:
            if not isinstance(item, dict):
                continue
            url = (item.get("url") or "").strip()
            if not url:
                continue
            found.append({
                "title": (item.get("title") or "").strip(),
                "url": url,
                "snippet": (item.get("content") or "").strip(),
                "score": item.get("score"),
            })
        return found
