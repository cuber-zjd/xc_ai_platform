from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.agent.insight import InsightCrawlerChannel, InsightTaskStatus
from app.services.agent.insight.crawler import discovery_checkpoint as checkpoint
from app.services.agent.insight.crawler.search_client import InsightSearchHit
from app.services.agent.insight.company_context import insight_company_material_rejection_reason


@pytest.mark.asyncio
async def test_checkpoint_replays_paid_search_with_publication_evidence(monkeypatch):
    saved = []
    session = AsyncMock()
    session.add = lambda task: saved.append(task)
    session.exec.side_effect = lambda query: SimpleNamespace(first=lambda: saved[-1] if saved else None)
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(checkpoint, "async_session", lambda: context)
    search = AsyncMock(return_value=([
        InsightSearchHit(channel=InsightCrawlerChannel.BOCHA, title="客户新品", url="https://example.com/a",
                         published_at=datetime(2026, 9, 7), raw={"date_verified": True})
    ], {"retry_count": 0}))
    await checkpoint.checkpointed_search("同一日期和查询", search)
    hits, meta = await checkpoint.checkpointed_search("同一日期和查询", search)
    assert search.await_count == 1
    assert hits[0].published_at == datetime(2026, 9, 7)
    assert hits[0].raw["date_verified"] is True
    assert meta["checkpoint_reused"] is True
    assert saved[-1].status == InsightTaskStatus.SUCCESS


def test_jianyuan_accepts_downstream_event_without_sugar_keyword():
    assert insight_company_material_rejection_reason("健源", {"title": "茶饮品牌新开工厂扩展供应链"}) is None
    assert insight_company_material_rejection_reason("健源", {"title": "国际航运船舶拍卖"})


def test_yuxin_still_excludes_vegetable_oil():
    assert insight_company_material_rejection_reason("御馨", {"title": "豆油品牌新增食用油产线"})
