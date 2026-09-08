import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import httpx

from app.services.agent.insight.crawler import search_client
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService
from app.core.config import settings


def mock_stream(monkeypatch, events):
    async def lines():
        for event in events:
            yield "data: " + json.dumps(event)
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.headers = {"x-request-id": "test-request"}
    response.aiter_lines = lines
    stream = AsyncMock()
    stream.__aenter__.return_value = response
    client = AsyncMock()
    client.stream = lambda *args, **kwargs: stream
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(search_client.httpx, "AsyncClient", lambda **kwargs: context)
    probe = search_client.DoubaoWebSearchClient()
    monkeypatch.setattr(probe, "_load_model_config", AsyncMock(return_value=SimpleNamespace(
        model_code="test", base_url="https://example.com", api_key="test")))
    return probe


@pytest.mark.asyncio
async def test_stream_disconnect_is_not_successful_empty_result(monkeypatch):
    probe = mock_stream(monkeypatch, [{"type": "response.output_text.delta", "delta": '{"items":[]}'}])
    with pytest.raises(RuntimeError, match="缺少完成事件"):
        await probe.search("食品", 3, "7d")


@pytest.mark.asyncio
async def test_completed_final_payload_without_deltas(monkeypatch):
    probe = mock_stream(monkeypatch, [{"type": "response.completed", "response": {
        "output": [{"content": [{"type": "output_text", "text": '{"items":[]}'}]}]
    }}])
    assert await probe.search("食品", 3, "7d") == []


@pytest.mark.asyncio
async def test_each_channel_uses_its_own_total_timeout(monkeypatch):
    service = InsightMonitorExecutionService()
    monkeypatch.setattr(service, "_search_grouped_channel", AsyncMock(return_value=[]))
    timeouts = []
    async def wait(coro, timeout):
        timeouts.append(timeout)
        return await coro
    monkeypatch.setattr(search_client.asyncio, "wait_for", wait)
    monkeypatch.setattr(settings, "INSIGHT_BOCHA_SEARCH_TOTAL_TIMEOUT_SECONDS", 45)
    monkeypatch.setattr(settings, "INSIGHT_DOUBAO_SEARCH_TOTAL_TIMEOUT_SECONDS", 350)
    batch = SimpleNamespace(rows=[1])
    await service._search_grouped_channel_with_retry(batch, "bocha")
    await service._search_grouped_channel_with_retry(batch, "doubao_web_search")
    assert timeouts == [45, 350]


@pytest.mark.asyncio
async def test_rate_limit_does_not_trigger_split_request_storm(monkeypatch):
    service = InsightMonitorExecutionService()
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
    search = AsyncMock(side_effect=httpx.HTTPStatusError("限流", request=response.request, response=response))
    monkeypatch.setattr(service, "_search_grouped_channel", search)
    with pytest.raises(httpx.HTTPStatusError):
        await service._search_grouped_channel_with_retry(SimpleNamespace(rows=[1, 2]), "doubao_web_search")
    assert search.await_count == 1
