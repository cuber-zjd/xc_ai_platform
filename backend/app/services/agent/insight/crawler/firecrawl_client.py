import asyncio
import ipaddress
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
        soup = BeautifulSoup(response.text, "lxml")
        for element in soup.select("script, style, noscript, nav, header, footer, form, aside"):
            element.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        lines = [line.strip() for line in root.get_text("\n").splitlines() if line.strip()]
        content = "\n".join(dict.fromkeys(lines))
        if len(content) < 200:
            raise ValueError("直接 HTTP 抽取未获得足够正文")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        metadata = {"title": title, "source_url": str(response.url)}
        for key in ("article:published_time", "publishdate", "pubdate", "date", "sailthru.date"):
            node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
            if node and node.get("content"):
                metadata["publishedTime"] = str(node.get("content"))
                break
        return {"markdown": content, "html": response.text, "metadata": metadata}

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
