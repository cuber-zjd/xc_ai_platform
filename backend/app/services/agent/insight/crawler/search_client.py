from dataclasses import dataclass
from datetime import datetime
from html import unescape
from re import DOTALL, IGNORECASE, compile as compile_regex, sub
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx

from app.core.config import settings
from app.models.agent.insight import InsightCrawlerChannel
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


@dataclass(slots=True)
class InsightSearchHit:
    channel: InsightCrawlerChannel
    title: str
    url: str
    snippet: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


class BaiduSearchClient:
    """百度搜索发现适配器，第一版仅抽取公开搜索结果标题和链接。"""

    _result_pattern = compile_regex(
        r"<h3[^>]*>.*?<a[^>]+href=[\"'](?P<url>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>.*?</h3>",
        IGNORECASE | DOTALL,
    )

    async def search(self, query: str, count: int) -> list[InsightSearchHit]:
        url = f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={count}"
        return await self._search_url(query, count, url, InsightCrawlerChannel.BAIDU, "baidu_html")

    async def search_news(self, query: str, count: int) -> list[InsightSearchHit]:
        url = f"https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&ie=utf-8&word={quote_plus(query)}&rn={count}"
        return await self._search_url(query, count, url, InsightCrawlerChannel.BAIDU_NEWS, "baidu_news_html")

    async def _search_url(
        self,
        query: str,
        count: int,
        url: str,
        channel: InsightCrawlerChannel,
        source: str,
    ) -> list[InsightSearchHit]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=settings.INSIGHT_SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

        hits: list[InsightSearchHit] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=settings.INSIGHT_SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
            for match in self._result_pattern.finditer(response.text):
                item_url = unescape(match.group("url")).strip()
                resolved_url = await self._resolve_result_url(client, item_url, headers)
                if not resolved_url or self._is_baidu_internal_url(resolved_url) or resolved_url in seen:
                    continue
                seen.add(resolved_url)
                title = self._clean_html(match.group("title"))
                context_html = response.text[match.start() : min(match.end() + 1200, len(response.text))]
                context_text = self._clean_html(context_html)
                hits.append(
                    InsightSearchHit(
                        channel=channel,
                        title=title or resolved_url,
                        url=resolved_url,
                        snippet=self._short_snippet(context_text, title),
                        published_at=insight_content_cleaner.parse_publish_time({}, context_text),
                        raw={"source": source, "query": query, "original_url": item_url, "search_context": context_text[:500]},
                    )
                )
                if len(hits) >= count:
                    break
        return hits

    async def _resolve_result_url(self, client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> str | None:
        if not url:
            return None
        if not self._is_baidu_redirect_url(url):
            return url
        try:
            response = await client.get(url, headers=headers)
        except httpx.HTTPError:
            return url
        return str(response.url)

    def _is_baidu_redirect_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc.endswith("baidu.com") and parsed.path.startswith("/link")

    def _is_baidu_internal_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host not in {"baidu.com", "www.baidu.com", "m.baidu.com"}:
            return False
        return parsed.path in {"", "/"} or parsed.path.startswith(("/s", "/link", "/sf", "/baidu"))

    def _clean_html(self, value: str) -> str:
        text = sub(r"<[^>]+>", "", value)
        text = unescape(text)
        return " ".join(text.split())

    def _short_snippet(self, context: str, title: str | None) -> str | None:
        text = context.replace(title or "", "", 1).strip()
        if not text:
            return None
        return text[:500]


class BochaSearchClient:
    """博查 Web Search API 适配器。

    官方开放平台当前入口为 POST /v1/web-search，使用 Bearer API Key。
    """

    async def search(self, query: str, count: int, freshness: str | None) -> list[InsightSearchHit]:
        if not settings.INSIGHT_BOCHA_API_KEY:
            raise ValueError("未配置 INSIGHT_BOCHA_API_KEY，无法调用 Bocha/博查搜索")

        endpoint = f"{settings.INSIGHT_BOCHA_BASE_URL.rstrip('/')}/v1/web-search"
        api_freshness = self._api_freshness(freshness)
        payload: dict[str, Any] = {
            "query": query,
            "count": count,
            "summary": True,
        }
        if api_freshness:
            payload["freshness"] = api_freshness

        headers = {
            "Authorization": f"Bearer {settings.INSIGHT_BOCHA_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=settings.INSIGHT_SEARCH_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return self._parse_response(data, count)

    def _api_freshness(self, freshness: str | None) -> str | None:
        value = (freshness or "").strip()
        if not value:
            return None
        lower_value = value.lower()
        if lower_value in {"halfmonth", "half_month", "15d", "recent15d", "recent_15d"}:
            return "oneMonth"
        return value

    def _parse_response(self, data: dict[str, Any], count: int) -> list[InsightSearchHit]:
        records = self._extract_records(data)
        hits: list[InsightSearchHit] = []
        seen: set[str] = set()
        for record in records:
            url = self._first_text(record.get("url"), record.get("link"), record.get("displayUrl"))
            if not url or url in seen:
                continue
            seen.add(url)
            title = self._first_text(record.get("name"), record.get("title"), url) or url
            snippet = self._first_text(record.get("summary"), record.get("snippet"), record.get("description"))
            published_at = (
                insight_content_cleaner.parse_publish_time(record)
                or insight_content_cleaner.parse_publish_time({}, snippet)
            )
            hits.append(
                InsightSearchHit(
                    channel=InsightCrawlerChannel.BOCHA,
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_at=published_at,
                    raw=record,
                )
            )
            if len(hits) >= count:
                break
        return hits

    def _extract_records(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            data.get("data", {}).get("webPages", {}).get("value"),
            data.get("data", {}).get("webpages", {}).get("value"),
            data.get("data", {}).get("results"),
            data.get("webPages", {}).get("value"),
            data.get("results"),
        ]
        for candidate in candidates:
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    def _first_text(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


baidu_search_client = BaiduSearchClient()
bocha_search_client = BochaSearchClient()
