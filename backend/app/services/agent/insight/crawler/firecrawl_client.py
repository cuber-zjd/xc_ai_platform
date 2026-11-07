import asyncio
import ipaddress
import json
import re
import socket
import time
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


class FulltextAccessBlocked(ValueError):
    """站点限制访问，本轮不切换引擎继续请求。"""


class FirecrawlClient:
    """本地 Firecrawl 服务客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.INSIGHT_FIRECRAWL_BASE_URL.rstrip("/")
        self.api_key = settings.INSIGHT_FIRECRAWL_API_KEY
        self.timeout_seconds = settings.INSIGHT_FIRECRAWL_TIMEOUT_SECONDS
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_next_request: dict[str, float] = {}
        self._blocked_until: dict[str, float] = {}

    def host_is_blocked(self, host: str) -> bool:
        return self._blocked_until.get(host, 0) > time.monotonic()

    @staticmethod
    def canonical_article_url(url: str) -> str:
        """只展开头条已知文章跳转，不接受跳转参数里的任意目标。"""
        parsed = urlparse(url)
        if parsed.hostname == "sou.toutiao.com" and parsed.path == "/search/jump":
            target = (parse_qs(parsed.query).get("url") or [""])[0]
            candidate = urlparse(target)
            if (candidate.hostname not in {"www.toutiao.com", "toutiao.com", "m.toutiao.com"}
                    or candidate.scheme not in {"http", "https"} or candidate.username or candidate.port):
                raise ValueError("头条跳转地址不是受支持的文章地址")
            parsed = candidate
            if not re.fullmatch(r"/(?:article/|a|i)(\d+)/?", parsed.path):
                raise ValueError("头条跳转目标不是文章路径")
        if parsed.hostname in {"www.toutiao.com", "toutiao.com", "m.toutiao.com"}:
            match = re.fullmatch(r"/(?:article/|a|i)(\d+)/?", parsed.path)
            if match:
                return f"https://www.toutiao.com/article/{match.group(1)}/"
        return url

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def scrape_url(self, url: str) -> dict[str, Any]:
        url = self.canonical_article_url(url)
        await self._ensure_public_url(url)
        if not self.is_configured:
            raise ValueError("未配置 INSIGHT_FIRECRAWL_BASE_URL，无法调用本地 Firecrawl")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "url": url,
            "formats": ["markdown", "html"],
            "onlyMainContent": True,
            # API 默认只等30秒，必须与客户端预算一致，并留出响应传输余量。
            "timeout": min(300000, max(1000, int((self.timeout_seconds - 5) * 1000))),
        }
        if (urlparse(url).hostname or "").endswith("toutiao.com"):
            payload["formats"].append("rawHtml")
        endpoint = f"{self.base_url}/v1/scrape"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if data.get("success") is False:
            raise ValueError(data.get("error") or "Firecrawl 抓取失败")
        return data.get("data") or data

    async def scrape_url_with_fallback(self, url: str) -> dict[str, Any]:
        original_url = url
        url = self.canonical_article_url(url)
        host = urlparse(url).hostname or ""
        async with self._host_locks.setdefault(host, asyncio.Lock()):
            if self.host_is_blocked(host):
                raise FulltextAccessBlocked(f"{host} 已触发访问限制，冷却中")
            await asyncio.sleep(max(0, self._host_next_request.get(host, 0) - time.monotonic()))
            try:
                data = await self._scrape_with_fallback(url)
                data["metadata"] = dict(data.get("metadata") or {}) | {
                    "original_source_url": original_url, "resolved_article_url": url,
                }
                return data
            except FulltextAccessBlocked:
                self._blocked_until[host] = time.monotonic() + 3600
                raise
            finally:
                self._host_next_request[host] = time.monotonic() + 2

    async def _scrape_with_fallback(self, url: str) -> dict[str, Any]:
        if self._prefer_direct_http(url):
            try:
                direct = await self._scrape_direct(url)
                metadata = dict(direct.get("metadata") or {})
                metadata["extractor"] = "direct_http"
                direct["metadata"] = metadata
                return direct
            except FulltextAccessBlocked:
                raise
            except Exception:
                pass
        try:
            firecrawl_data = await self.scrape_url(url)
            metadata = firecrawl_data.get("metadata") or {}
            if metadata.get("statusCode") in {403, 429}:
                raise FulltextAccessBlocked(f"站点限制访问 HTTP {metadata['statusCode']}")
            if firecrawl_data.get("rawHtml") or firecrawl_data.get("html"):
                # rawHtml 保留 JSON-LD；清洗后的 html 会丢失发布时间，只剩相对时间。
                soup = BeautifulSoup(firecrawl_data.get("rawHtml") or firecrawl_data["html"], "lxml")
                self._check_verification_page(soup.get_text(" ", strip=True))
                page_metadata = self._extract_page_metadata(soup, url)
                firecrawl_data["metadata"] = dict(firecrawl_data.get("metadata") or {}) | page_metadata
                if (urlparse(url).hostname or "").endswith("toutiao.com"):
                    root = soup.find("article") or soup.select_one(".article-content")
                    if root is None:
                        raise ValueError("头条页面未找到文章容器，不使用推荐流或脚本外壳")
                    firecrawl_data["markdown"] = root.get_text("\n", strip=True)
                    firecrawl_data["metadata"]["body_selector"] = "article/.article-content"
                    title = soup.select_one("h1.article__title") or soup.find("h1")
                    if title:
                        firecrawl_data["metadata"]["title"] = title.get_text(" ", strip=True)
            content = str(firecrawl_data.get("markdown") or firecrawl_data.get("content") or "")
            self._check_verification_page(content)
            if not insight_content_cleaner.fulltext_error(content):
                return firecrawl_data
            raise ValueError("Firecrawl 未返回足够正文")
        except FulltextAccessBlocked:
            raise
        except Exception as firecrawl_error:
            try:
                direct = await self._scrape_direct(url)
            except FulltextAccessBlocked:
                raise
            except Exception as direct_error:
                raise ValueError(
                    f"Firecrawl: {type(firecrawl_error).__name__}: {str(firecrawl_error)[:180]}; "
                    f"HTTP: {type(direct_error).__name__}: {str(direct_error)[:240]}"
                ) from direct_error
            metadata = dict(direct.get("metadata") or {})
            metadata["extractor"] = "direct_http_fallback"
            metadata["firecrawl_error"] = str(firecrawl_error)[:500]
            direct["metadata"] = metadata
            return direct

    def _prefer_direct_http(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        direct_hosts = ("gov.cn", "sse.com.cn", "szse.cn", "bse.cn", "cninfo.com.cn", "wipo.int")
        return any(host == value or host.endswith(f".{value}") for value in direct_hosts)

    async def _scrape_direct(self, url: str) -> dict[str, Any]:
        await self._ensure_public_url(url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
            )
        }
        timeout = min(max(self.timeout_seconds, 10), 30)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
            response = await self._get_public_page(client, url)
        response_text = self._decode_response_text(response)
        soup = BeautifulSoup(response_text, "lxml")
        self._check_verification_page(soup.get_text(" ", strip=True))
        metadata = self._extract_page_metadata(soup, str(response.url))
        metadata_url = self._metadata_fallback_url(str(response.url))
        if not metadata.get("publishedTime") and not metadata.get("publication_conflict") and metadata_url:
            try:
                await self._ensure_public_url(metadata_url)
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=False,
                    headers=headers,
                ) as metadata_client:
                    metadata_response = await self._get_public_page(metadata_client, metadata_url)
                desktop_metadata = self._extract_page_metadata(
                    BeautifulSoup(self._decode_response_text(metadata_response), "lxml"),
                    str(metadata_response.url),
                )
                metadata = metadata | desktop_metadata
            except Exception as exc:
                metadata["metadata_fallback_error"] = str(exc)[:300]
        for element in soup.select("script, style, noscript, nav, header, footer, form, aside"):
            element.decompose()
        root = soup.find("article") or soup.select_one(".article-content")
        if (urlparse(url).hostname or "").endswith("toutiao.com") and root is None:
            raise ValueError("头条返回脚本外壳，未获得文章正文；不将搜索页或推荐内容当正文")
        root = root or soup.find("main") or soup.body or soup
        lines = [line.strip() for line in root.get_text("\n").splitlines() if line.strip()]
        content = "\n".join(dict.fromkeys(lines))
        if error := insight_content_cleaner.fulltext_error(content):
            raise ValueError(error)
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        metadata["title"] = metadata.get("title") or title
        return {"markdown": content, "html": response_text, "metadata": metadata}

    @staticmethod
    def _check_verification_page(text: str) -> None:
        if len(text) < 2000 and any(value in text.lower() for value in (
            "安全验证", "访问过于频繁", "完成验证后继续", "captcha", "verify you are human",
        )):
            raise FulltextAccessBlocked("站点返回安全验证或访问限制页面，停止本轮请求")

    async def _get_public_page(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """正文和元数据补抓共用逐跳地址校验及流式大小限制。"""
        current_url = url
        limit = 5 * 1024 * 1024
        for _ in range(6):
            await self._ensure_public_url(current_url)
            async with client.stream("GET", current_url, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("网页重定向缺少目标地址")
                    current_url = urljoin(current_url, location)
                    if "captcha" in (urlparse(current_url).hostname or ""):
                        raise FulltextAccessBlocked("站点跳转到验证码页面")
                    continue
                if response.status_code in {403, 429}:
                    raise FulltextAccessBlocked(f"站点限制访问 HTTP {response.status_code}")
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(value in content_type for value in ("text/html", "text/plain", "application/xhtml+xml")):
                    raise ValueError(f"直接 HTTP 抽取不支持该内容类型：{content_type[:100]}")
                chunks = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("网页内容超过 5MB，停止直接抽取")
                    chunks.append(chunk)
                # 数据已经解压，重建响应时不能再次应用原 Content-Encoding。
                headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-encoding", "content-length"}}
                return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks), request=response.request)
        raise ValueError("网页重定向次数过多")

    @staticmethod
    def _decode_response_text(response: httpx.Response) -> str:
        """按页面声明和字节可解码性处理中文媒体常见的 GBK/GB2312 页面。"""
        content = response.content
        if not content:
            return ""

        head = content[:8192].decode("ascii", errors="ignore")
        meta_match = re.search(
            r"charset\s*=\s*['\"]?\s*([a-zA-Z0-9._-]+)",
            head,
            flags=re.IGNORECASE,
        )
        candidates: list[str] = []
        if meta_match:
            candidates.append(meta_match.group(1))
        content_type = response.headers.get("content-type", "")
        header_match = re.search(r"charset\s*=\s*([a-zA-Z0-9._-]+)", content_type, re.IGNORECASE)
        if header_match:
            candidates.append(header_match.group(1))
        candidates.extend(("utf-8", "gb18030"))

        seen: set[str] = set()
        for candidate in candidates:
            normalized = candidate.strip().lower().replace("_", "-")
            if normalized in {"gbk", "gb2312", "x-gbk"}:
                normalized = "gb18030"
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            try:
                return content.decode(normalized)
            except (LookupError, UnicodeDecodeError):
                continue
        return content.decode("utf-8", errors="replace")

    def _extract_page_metadata(self, soup: BeautifulSoup, source_url: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {"source_url": source_url}
        if soup.title:
            metadata["title"] = soup.title.get_text(" ", strip=True)
        evidence: list[dict[str, str]] = []
        selectors = (
            ".article-title-icon .item-time", ".article-info .info-s",
            ".article-info", "article time[datetime]", "[itemprop='datePublished']",
            ".publish-time", ".publish_time", ".pub-time", ".article-time",
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                value = str(node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)).strip()
                if value:
                    evidence.append({"kind": "header", "location": selector, "raw": value})
        host = (urlparse(source_url).hostname or "").lower()
        if host == "news.foodmate.net" and urlparse(source_url).path.startswith("/wap/"):
            node = soup.select_one("div.info")
            value = node.get_text(" ", strip=True) if node else ""
            visible = re.match(r"日期\s*[:：]\s*(20\d{2}-\d{1,2}-\d{1,2})", value)
            if visible:
                evidence.insert(0, {"kind": "header", "location": "foodmate wap div.info 日期", "raw": visible.group(1)})
        if host in {"www.roquette.com", "roquette.com"}:
            # 仅取文章头部明确的 Published 字段，不能从相关文章日期补值。
            root = soup.find("article") or soup.find("main")
            head = root.get_text(" ", strip=True)[:1200] if root else ""
            visible = re.search(r"Published\s*(?:on|:)?\s*((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2})", head)
            if visible:
                evidence.insert(0, {"kind": "header", "location": "article Published", "raw": visible.group(1)})
        date_keys = {"article:published_time", "og:published_time", "publishdate",
                     "pubdate", "datepublished", "publish_time", "publishtime", "sailthru.date"}
        for node in soup.find_all("meta"):
            key = str(node.get("property") or node.get("name") or node.get("itemprop") or "").lower()
            value = str(node.get("content") or "").strip()
            if key in date_keys and value:
                evidence.append({"kind": "metadata", "location": key, "raw": value})
        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(node.string or node.get_text() or "")
            except (TypeError, ValueError):
                continue
            if value := self._find_json_date(payload):
                evidence.append({"kind": "jsonld", "location": "datePublished", "raw": value})
        valid = []
        for item in evidence:
            # 只有带年份的绝对日期可成为发布证据，不能把刷新/相对时间当成今天。
            if not re.search(r"\b20\d{2}\b|20\d{2}年", item["raw"]):
                continue
            parsed, _ = insight_content_cleaner.parse_publish_time_with_source({"publishedTime": item["raw"]})
            if parsed:
                item["value"] = parsed.isoformat()
                valid.append(item)
        metadata["publication_evidence"] = valid
        if not valid:
            return metadata
        dates = {item["value"][:10] for item in valid}
        # 已有回归证实36氪SEO时间会随页面刷新；仅该站保留可见头部优先规则。
        known_dynamic_seo = host in {"36kr.com", "www.36kr.com"} and valid[0]["kind"] == "header"
        if len(dates) > 1 and not known_dynamic_seo:
            metadata["publication_conflict"] = True
        else:
            metadata["publishedTime"] = valid[0]["raw"]
            if len(dates) > 1:
                metadata["publication_resolution"] = "36kr_visible_header_over_dynamic_seo"
        return metadata

    def _find_json_date(self, value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("datePublished", "publishTime", "publishedAt"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for key, child in value.items():
                if key not in {"@graph", "mainEntity", "mainEntityOfPage"}:
                    continue
                found = self._find_json_date(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._find_json_date(child)
                if found:
                    return found
        return None

    def _metadata_fallback_url(self, source_url: str) -> str | None:
        parsed = urlparse(source_url)
        host_map = {"m.jiemian.com": "www.jiemian.com"}
        target_host = host_map.get((parsed.hostname or "").lower())
        if not target_host:
            return None
        port = f":{parsed.port}" if parsed.port else ""
        return parsed._replace(netloc=f"{target_host}{port}").geturl()

    async def _ensure_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("仅允许抓取公开 HTTP/HTTPS 地址")
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            raise ValueError("禁止直接抓取本机地址")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal and self._is_blocked_address(literal):
            raise ValueError("禁止直接抓取内网地址")
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            parsed.port or default_port,
            type=socket.SOCK_STREAM,
        )
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if self._is_blocked_address(ip):
                raise ValueError("目标域名解析到内网地址，停止直接抓取")

    def _is_blocked_address(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            return True
        blocked_networks = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("fc00::/7"),
        )
        return any(ip in network for network in blocked_networks if ip.version == network.version)


firecrawl_client = FirecrawlClient()
