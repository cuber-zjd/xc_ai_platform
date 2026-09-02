import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest
from app.services.agent.insight.crawler.search_client import (
    BaiduAntiBotError,
    BaiduCircuitOpenError,
    BaiduSearchClient,
    baidu_search_client,
)
from app.services.agent.insight.crawler.search_service import insight_search_discovery_service
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService
from app.services.agent.insight.scheduler_service import InsightSchedulerService


def _response(*, url: str, status_code: int = 200, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, text=text, request=request)


def test_baidu_antibot_response_detects_redirect_and_page_marker() -> None:
    client = BaiduSearchClient()

    assert client._is_antibot_response(
        _response(url="https://wappass.baidu.com/static/captcha/tuxing_v2.html")
    )
    assert client._is_antibot_response(
        _response(url="https://www.baidu.com/s", text="<title>百度安全验证</title>")
    )
    assert not client._is_antibot_response(
        _response(url="https://www.baidu.com/s", text="<title>百度资讯搜索结果</title>")
    )


def test_baidu_antibot_opens_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BaiduSearchClient()
    client._write_persistent_blocked_until = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent.insight.crawler.search_client.settings.INSIGHT_BAIDU_ANTIBOT_COOLDOWN_SECONDS",
        600,
    )

    with pytest.raises(BaiduAntiBotError):
        asyncio.run(
            client._open_antibot_circuit(
                _response(url="https://wappass.baidu.com/static/captcha/tuxing_v2.html")
            )
        )

    assert client._blocked_until is not None
    assert client._blocked_until > datetime.now() + timedelta(seconds=590)
    client._read_persistent_blocked_until = AsyncMock(return_value=None)
    with pytest.raises(BaiduCircuitOpenError):
        asyncio.run(client._raise_if_circuit_open())


def test_baidu_expired_circuit_is_released() -> None:
    client = BaiduSearchClient()
    client._blocked_until = datetime.now() - timedelta(seconds=1)
    client._read_persistent_blocked_until = AsyncMock(return_value=None)

    asyncio.run(client._raise_if_circuit_open())

    assert client._blocked_until is None


@pytest.mark.asyncio
async def test_baidu_only_discovery_preserves_antibot_error() -> None:
    request = InsightSearchDiscoveryRequest(
        query="玉米糖浆",
        channels=["baidu_news"],
        max_results=3,
        crawl_top_n=0,
    )
    with patch.object(
        baidu_search_client,
        "search_news",
        AsyncMock(side_effect=BaiduAntiBotError("百度资讯触发安全验证")),
    ):
        with pytest.raises(BaiduAntiBotError):
            await insight_search_discovery_service._collect_hits(None, request)


def test_baidu_slots_cover_every_monitor_once_per_day() -> None:
    rows = [SimpleNamespace(id=index) for index in range(1, 181)]
    assigned_ids = [
        row.id
        for slot_index in range(144)
        for row in InsightMonitorExecutionService._rows_for_baidu_slot(
            rows, slot_index, 144
        )
    ]

    assert sorted(assigned_ids) == list(range(1, 181))
    assert len(assigned_ids) == len(set(assigned_ids))


def test_baidu_slot_context_uses_144_ten_minute_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.agent.insight.scheduler_service.settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS",
        600,
    )
    scheduler = InsightSchedulerService()

    slot_index, slot_count = scheduler._baidu_slot_context(
        datetime(2026, 9, 2, 13, 40, 30)
    )

    assert slot_count == 144
    assert slot_index == 82
