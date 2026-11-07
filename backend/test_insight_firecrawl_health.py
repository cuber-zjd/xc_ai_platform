import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scripts import insight_check_firecrawl as health


@pytest.mark.asyncio
@pytest.mark.parametrize("failed,previous,level,recovered", [
    (True, [], "warning", False),
    (True, ["failed", "failed"], "critical", False),
    (False, ["failed"], "none", True),
])
async def test_actual_probe_alert_and_recovery(monkeypatch, failed, previous, level, recovered):
    monkeypatch.setenv("INSIGHT_FIRECRAWL_PROBE_TARGETS", json.dumps([
        {"url": "https://example.org/test", "expected": "项目投产"},
    ]))
    client = SimpleNamespace(scrape_url=AsyncMock(), _check_verification_page=Mock())
    if failed:
        client.scrape_url.side_effect = TimeoutError("探针超时")
    else:
        client.scrape_url.return_value = {"markdown": "项目投产，新增生产线及业务合作。" * 30}
    monkeypatch.setattr(health, "FirecrawlClient", lambda: client)
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(all=lambda: [SimpleNamespace(status=value) for value in previous])
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr(health, "async_session", lambda: context)
    result = await health.probe()
    assert result["alert"] == level
    assert result["recovered"] == recovered
    assert "insight_probe=" in client.scrape_url.await_args.args[0]
    assert db.add.call_args.args[0].task_type == "firecrawl_health"
