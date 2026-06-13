from typing import Any

import httpx

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


firecrawl_client = FirecrawlClient()
