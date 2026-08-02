import asyncio
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings


class FirecrawlClient:
    """本地 Firecrawl 服务客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.INSIGHT_FIRECRAWL_BASE_URL.rstrip("/")
        self.api_key = settings.INSIGHT_FIRECRAWL_API_KEY
        self.timeout_seconds = settings.INSIGHT_FIRECRAWL_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def scrape_url(self, url: str) -> dict[str, Any]:
        if not self.is_configured:
            raise ValueError("未配置 INSIGHT_FIRECRAWL_BASE_URL，无法调用本地 Firecrawl")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "url": url,
            "formats": ["markdown", "html"],
            "onlyMainContent": True,
        }
        endpoint = f"{self.base_url}/v1/scrape"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if data.get("success") is False:
            raise ValueError(data.get("error") or "Firecrawl 抓取失败")
        return data.get("data") or data

    async def scrape_url_with_fallback(self, url: str) -> dict[str, Any]:
        if self._prefer_direct_http(url):
            try:
                direct = await self._scrape_direct(url)
                metadata = dict(direct.get("metadata") or {})
                metadata["extractor"] = "direct_http"
                direct["metadata"] = metadata
                return direct
            except Exception:
                pass
        try:
            firecrawl_data = await self.scrape_url(url)
            content = str(firecrawl_data.get("markdown") or firecrawl_data.get("content") or "")
            if len(content.strip()) >= 200:
                return firecrawl_data
            raise ValueError("Firecrawl 未返回足够正文")
        except Exception as firecrawl_error:
            direct = await self._scrape_direct(url)
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
            current_url = url
            response = None
            for _ in range(6):
                await self._ensure_public_url(current_url)
                response = await client.get(current_url)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current_url = urljoin(current_url, location)
                    continue
                break
            if response is None or response.is_redirect:
                raise ValueError("网页重定向次数过多")
            response.raise_for_status()
            if len(response.content) > 5 * 1024 * 1024:
                raise ValueError("网页内容超过 5MB，停止直接抽取")
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not any(
                value in content_type
                for value in ("text/html", "text/plain", "application/xhtml+xml")
            ):
                raise ValueError(f"直接 HTTP 抽取不支持该内容类型：{content_type[:100]}")
        response_text = self._decode_response_text(response)
        soup = BeautifulSoup(response_text, "lxml")
        metadata = self._extract_page_metadata(soup, str(response.url))
        metadata_url = self._metadata_fallback_url(str(response.url))
        if not metadata.get("publishedTime") and metadata_url:
            try:
                await self._ensure_public_url(metadata_url)
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=headers,
                ) as metadata_client:
                    metadata_response = await metadata_client.get(metadata_url)
                    metadata_response.raise_for_status()
                desktop_metadata = self._extract_page_metadata(
                    BeautifulSoup(self._decode_response_text(metadata_response), "lxml"),
                    str(metadata_response.url),
                )
                metadata = metadata | desktop_metadata
            except Exception as exc:
                metadata["metadata_fallback_error"] = str(exc)[:300]
        for element in soup.select("script, style, noscript, nav, header, footer, form, aside"):
            element.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        lines = [line.strip() for line in root.get_text("\n").splitlines() if line.strip()]
        content = "\n".join(dict.fromkeys(lines))
        if len(content) < 200:
            raise ValueError("直接 HTTP 抽取未获得足够正文")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        metadata["title"] = metadata.get("title") or title
        return {"markdown": content, "html": response_text, "metadata": metadata}

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
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        if title:
            metadata["title"] = title

        # 部分媒体的动态 SEO 标签会写成页面刷新时间，优先读取文章头部的可见发布时间。
        for selector in (
            ".article-title-icon .item-time",
            ".article-info .info-s",
            ".article-info",
            "time[datetime]",
            "[itemprop='datePublished']",
        ):
            node = soup.select_one(selector)
            if not node:
                continue
            value = str(node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)).strip()
            if value:
                metadata["publishedTime"] = value
                return metadata

        date_keys = {
            "article:published_time",
            "og:published_time",
            "publishdate",
            "pubdate",
            "date",
            "datepublished",
            "publish_time",
            "publishtime",
            "sailthru.date",
        }
        for node in soup.find_all("meta"):
            key = str(node.get("property") or node.get("name") or node.get("itemprop") or "").lower()
            content = str(node.get("content") or "").strip()
            if key in date_keys and content:
                metadata["publishedTime"] = content
                return metadata

        for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(node.string or node.get_text() or "")
            except (TypeError, ValueError):
                continue
            published = self._find_json_date(payload)
            if published:
                metadata["publishedTime"] = published
                return metadata

        for selector in (
            ".publish-time",
            ".publish_time",
            ".pub-time",
            ".article-time",
        ):
            node = soup.select_one(selector)
            if not node:
                continue
            value = str(node.get("datetime") or node.get("content") or node.get_text(" ", strip=True)).strip()
            if value:
                metadata["publishedTime"] = value
                return metadata
        return metadata

    def _find_json_date(self, value: Any) -> str | None:
        if isinstance(value, dict):
            for key in ("datePublished", "dateCreated", "publishTime", "publishedAt"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for child in value.values():
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
