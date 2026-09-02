from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
import asyncio
import json
import random
import re
from re import DOTALL, IGNORECASE, compile as compile_regex, sub
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import quote_plus, urlparse

import httpx
from sqlalchemy import or_
from sqlmodel import select

from app.core.config import settings
from app.core.llm_usage import record_llm_usage_payload
from app.db.session import async_session
from app.models.agent.insight import InsightCrawlerChannel
from app.models.system.sys_model import SysModel
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


@dataclass(slots=True)
class InsightSearchHit:
    channel: InsightCrawlerChannel
    title: str
    url: str
    snippet: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] | None = None


class BaiduSearchUnavailableError(RuntimeError):
    """百度当前不可用，调用方应停止密集重试。"""


class BaiduAntiBotError(BaiduSearchUnavailableError):
    """百度返回了安全验证或限流页面。"""


class BaiduCircuitOpenError(BaiduSearchUnavailableError):
    """百度反爬熔断期内跳过请求。"""


class BaiduSearchClient:
    """百度搜索发现适配器，第一版仅抽取公开搜索结果标题和链接。"""

    _result_pattern = compile_regex(
        r"<h3[^>]*>.*?<a[^>]+href=[\"'](?P<url>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>.*?</h3>",
        IGNORECASE | DOTALL,
    )
    _antibot_markers = (
        "百度安全验证",
        "请输入验证码",
        "网络不给力，请稍后重试",
        "wappass.baidu.com",
        "captcha",
    )

    def __init__(self) -> None:
        self._request_lock = asyncio.Lock()
        self._blocked_until: datetime | None = None

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
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
        async with self._request_lock:
            self._raise_if_circuit_open()
            await asyncio.sleep(random.uniform(0.8, 1.8))
            async with httpx.AsyncClient(
                timeout=settings.INSIGHT_SEARCH_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
                if self._is_antibot_response(response):
                    self._open_antibot_circuit(response)
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
                snippet = self._short_snippet(context_text, title)
                hits.append(
                    InsightSearchHit(
                        channel=channel,
                        title=title or resolved_url,
                        url=resolved_url,
                        snippet=snippet,
                        published_at=insight_content_cleaner.parse_publish_time({}, snippet, context_text),
                        raw={"source": source, "query": query, "original_url": item_url, "search_context": context_text[:500]},
                    )
                )
                if len(hits) >= count:
                    break
        return hits

    def _raise_if_circuit_open(self) -> None:
        if not self._blocked_until:
            return
        now = datetime.now()
        if now >= self._blocked_until:
            self._blocked_until = None
            return
        remaining_seconds = max(int((self._blocked_until - now).total_seconds()), 1)
        raise BaiduCircuitOpenError(
            f"百度安全验证熔断中，剩余约 {remaining_seconds} 秒，已跳过请求"
        )

    def _is_antibot_response(self, response: httpx.Response) -> bool:
        host = (response.url.host or "").lower()
        if host == "wappass.baidu.com" or host.endswith(".wappass.baidu.com"):
            return True
        if response.status_code in {403, 429}:
            return True
        text = response.text[:20000].lower()
        return any(marker.lower() in text for marker in self._antibot_markers)

    def _open_antibot_circuit(self, response: httpx.Response) -> None:
        cooldown_seconds = max(settings.INSIGHT_BAIDU_ANTIBOT_COOLDOWN_SECONDS, 300)
        self._blocked_until = datetime.now() + timedelta(seconds=cooldown_seconds)
        raise BaiduAntiBotError(
            "百度返回安全验证/限流页面，已熔断后续百度请求；"
            f"HTTP {response.status_code}，最终地址 {response.url.host or '未知'}，"
            f"冷却 {cooldown_seconds} 秒"
        )

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
        day_match = re.fullmatch(r"(\d+)\s*d", lower_value)
        if day_match:
            days = int(day_match.group(1))
            if days <= 1:
                return "oneDay"
            if days <= 7:
                return "oneWeek"
            if days <= 30:
                return "oneMonth"
            return "noLimit"
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


class DoubaoWebSearchClient:
    """火山方舟 Responses API 联网搜索适配器。

    豆包联网搜索不是传统搜索 API，流式返回里主要包含搜索动作、引用标注和最终回答。
    因此这里要求模型把可入库线索整理为 JSON，再保留原始搜索动作和引用，作为审计信息。
    """

    preferred_model_code = "doubao-seed-2-1-turbo-260628"

    async def search(self, query: str, count: int, freshness: str | None) -> list[InsightSearchHit]:
        model = await self._load_model_config()
        endpoint = f"{model.base_url.rstrip('/')}/responses"
        prompt = self._build_prompt(query, count, freshness)
        payload = {
            "model": model.model_code,
            "stream": True,
            "tools": [{"type": "web_search"}],
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {model.api_key}",
            "Content-Type": "application/json",
        }
        text_parts: list[str] = []
        web_queries: list[str] = []
        annotations: list[dict[str, Any]] = []
        event_samples: list[dict[str, Any]] = []
        response_usage: dict[str, Any] | None = None

        timeout = httpx.Timeout(
            connect=max(settings.INSIGHT_DOUBAO_SEARCH_CONNECT_TIMEOUT_SECONDS, 5),
            read=max(settings.INSIGHT_DOUBAO_SEARCH_READ_TIMEOUT_SECONDS, 90),
            write=max(settings.INSIGHT_SEARCH_TIMEOUT_SECONDS, 30),
            pool=max(settings.INSIGHT_SEARCH_TIMEOUT_SECONDS, 30),
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_text = line.removeprefix("data:").strip()
                    if not data_text or data_text == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue
                    event_type = str(event.get("type") or "")
                    if len(event_samples) < 40:
                        event_samples.append(self._event_excerpt(event))
                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if isinstance(delta, str):
                            text_parts.append(delta)
                    if event_type == "response.output_text.annotation.added":
                        annotation = event.get("annotation")
                        if isinstance(annotation, dict):
                            annotations.append(annotation)
                    query_text = self._extract_web_query(event)
                    if query_text and query_text not in web_queries:
                        web_queries.append(query_text)
                    usage = event.get("usage")
                    response_payload = event.get("response")
                    if not isinstance(usage, dict) and isinstance(response_payload, dict):
                        usage = response_payload.get("usage")
                    if isinstance(usage, dict):
                        response_usage = usage

        answer_text = "".join(text_parts).strip()
        record_llm_usage_payload(model.model_code, response_usage)
        raw_context = {
            "source_channel": "doubao_web_search",
            "model": model.model_code,
            "search_queries": web_queries,
            "annotations": annotations[:50],
            "answer_text": answer_text,
            "event_samples": event_samples,
        }
        return self._parse_answer(answer_text, raw_context, count)

    async def _load_model_config(self) -> SysModel:
        async with async_session() as session:
            exact = (
                await session.exec(
                    select(SysModel).where(
                        SysModel.is_deleted == 0,
                        SysModel.is_enabled,
                        SysModel.model_type == "chat",
                        or_(
                            SysModel.model_code == self.preferred_model_code,
                            SysModel.model_name == self.preferred_model_code,
                        ),
                    )
                )
            ).first()
            if exact:
                return exact
            volc = (
                await session.exec(
                    select(SysModel)
                    .where(
                        SysModel.is_deleted == 0,
                        SysModel.is_enabled,
                        SysModel.model_type == "chat",
                        SysModel.provider == "volcengine",
                    )
                    .order_by(SysModel.model_level, SysModel.priority)
                )
            ).first()
            if volc:
                return volc
        raise ValueError("未找到可用于豆包联网搜索的火山方舟 chat 模型配置")

    def _build_prompt(self, query: str, count: int, freshness: str | None) -> str:
        time_hint = "近 15 天"
        value = (freshness or "").strip().lower()
        day_match = re.fullmatch(r"(\d+)\s*d", value)
        if day_match:
            time_hint = f"近 {max(int(day_match.group(1)), 1)} 天"
        elif value in {"oneweek", "one_week", "week", "7d"}:
            time_hint = "近 7 天"
        elif value in {"oneday", "one_day", "day", "24h"}:
            time_hint = "近 24 小时"
        elif value in {"onemonth", "one_month", "month", "30d"}:
            time_hint = "近 30 天"
        return (
            f"请联网搜索“{query}”相关的公开资讯，优先选择{time_hint}内的信息。"
            "只保留与食品饮料、农产品加工、粮油、大豆/玉米加工、功能糖/糖浆、植物蛋白、"
            "客户/竞对动态、政策监管、技术专利、市场价格和风险舆情相关的内容。"
            f"最多返回 {max(1, count)} 条。"
            "请只输出严格 JSON，不要输出解释文字，格式为："
            "{\"items\":[{\"title\":\"标题\",\"url\":\"原文链接\",\"summary\":\"一句话摘要\","
            "\"source\":\"来源\",\"published_at\":\"YYYY-MM-DD 或空字符串\",\"why\":\"为什么值得关注\"}]}"
        )

    def _extract_web_query(self, event: dict[str, Any]) -> str | None:
        candidates = [
            event.get("query"),
            event.get("action", {}).get("query") if isinstance(event.get("action"), dict) else None,
            event.get("item", {}).get("action", {}).get("query") if isinstance(event.get("item"), dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _event_excerpt(self, event: dict[str, Any]) -> dict[str, Any]:
        result = {"type": event.get("type")}
        query = self._extract_web_query(event)
        if query:
            result["query"] = query
        annotation = event.get("annotation")
        if isinstance(annotation, dict):
            result["annotation"] = {key: annotation.get(key) for key in ("type", "title", "url", "text")}
        return result

    def _parse_answer(self, answer_text: str, raw_context: dict[str, Any], count: int) -> list[InsightSearchHit]:
        records = self._json_records(answer_text)
        if not records:
            records = self._markdown_records(answer_text)
        hits: list[InsightSearchHit] = []
        seen: set[str] = set()
        for record in records:
            url = self._clean_result_url(self._first_text(record.get("url"), record.get("link")))
            if not url or url in seen:
                continue
            seen.add(url)
            title = self._first_text(record.get("title"), record.get("name"), url) or url
            summary = self._first_text(record.get("summary"), record.get("why"), record.get("snippet"))
            published_at = (
                insight_content_cleaner.parse_publish_time(record)
                or insight_content_cleaner.parse_publish_time({}, self._first_text(record.get("published_at"), summary))
            )
            hits.append(
                InsightSearchHit(
                    channel=InsightCrawlerChannel.DOUBAO_WEB_SEARCH,
                    title=title,
                    url=url,
                    snippet=summary,
                    published_at=published_at,
                    raw=raw_context | {"item": record},
                )
            )
            if len(hits) >= count:
                break
        return hits

    def _clean_result_url(self, value: str | None) -> str | None:
        if not value:
            return None
        matched = re.match(r"https?://[^\s\"'<>}\]]+", value.strip(), flags=re.IGNORECASE)
        if not matched:
            return None
        url = matched.group(0).rstrip("。；，,、.)）]")
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        return url

    def _json_records(self, text: str) -> list[dict[str, Any]]:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?", "", value, flags=re.IGNORECASE).strip()
            value = re.sub(r"```$", "", value).strip()
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [item for item in data["items"] if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _markdown_records(self, text: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            if "|" not in line or "---" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 2:
                continue
            joined = " ".join(cells)
            url_match = re.search(r"\((https?://[^)]+)\)", joined) or re.search(r"(https?://\S+)", joined)
            if not url_match:
                continue
            title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cells[0]).strip()
            records.append(
                {
                    "title": title or cells[0],
                    "url": url_match.group(1).rstrip("。；,，"),
                    "published_at": cells[1] if len(cells) > 1 else "",
                    "source": cells[2] if len(cells) > 2 else "",
                    "summary": cells[-1] if cells else "",
                }
            )
        return records

    def _first_text(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


baidu_search_client = BaiduSearchClient()
bocha_search_client = BochaSearchClient()
doubao_web_search_client = DoubaoWebSearchClient()
