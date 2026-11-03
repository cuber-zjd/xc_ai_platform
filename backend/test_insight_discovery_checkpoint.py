from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.agent.insight import InsightCrawlerChannel, InsightTaskStatus
from app.services.agent.insight.crawler import discovery_checkpoint as checkpoint
from app.services.agent.insight.crawler.search_client import InsightSearchHit, DoubaoWebSearchClient
from app.services.agent.insight.company_context import insight_company_material_rejection_reason
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService
from app.models.agent.insight import InsightChannel, InsightMonitorConfig, InsightTask
from app.models.agent.insight import InsightCrawlResult
from app.services.agent.insight.crawler.search_service import InsightSearchDiscoveryService, insight_crawl_service


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


def test_doubao_unselected_citations_are_not_news_hits():
    with pytest.raises(ValueError, match="格式无效"):
        DoubaoWebSearchClient()._parse_answer("资料见引用", {"annotations": [
            {"url": "https://example.com/a", "title": "食品客户动态"},
            {"url": "https://example.com/a", "title": "重复引用"},
        ]}, 10)


@pytest.mark.asyncio
async def test_baidu_recovers_missed_slot_without_repeating_completed(monkeypatch):
    service = InsightMonitorExecutionService()
    rows = [InsightMonitorConfig(id=i, config_code=f"monitor_{i}", config_name=f"监测{i}",
                                monitor_type="industry", object_type="custom", object_name=f"主题{i}")
            for i in (1, 2, 3, 4)]
    previous = InsightTask(task_uid="previous", task_type="baidu_spread_tick", output_payload={
        "executions": [{"monitor_config_id": 1, "status": "success"},
                       {"monitor_config_id": 2, "status": "failed"},
                       {"monitor_config_id": 2, "status": "failed"}]
    })
    db = AsyncMock()
    db.exec.side_effect = [SimpleNamespace(all=lambda: rows), SimpleNamespace(all=lambda: [previous])]
    monkeypatch.setattr(service, "_active_channels", AsyncMock(return_value=[
        InsightChannel(id=1, channel_code="baidu_news", channel_name="百度")
    ]))
    run = AsyncMock(return_value={"status": "success", "hits": 1, "candidates": 1})
    monkeypatch.setattr(service, "_run_baidu_monitor_row", run)
    await service.run_baidu_discovery_slot(db, slot_index=4, slot_count=144)
    assert [call.args[0].id for call in run.await_args_list] == [3, 4]


@pytest.mark.asyncio
async def test_fulltext_retry_preserves_original_window_and_attempt_limit(monkeypatch):
    service = InsightSearchDiscoveryService()
    start = datetime.now() - timedelta(days=3)
    end = start + timedelta(days=1)
    task = InsightTask(task_uid="original", task_type="search_discovery", create_time=end,
                       input_payload={"query": "食品新品", "published_start": start.isoformat(), "published_end": end.isoformat()})
    result = InsightCrawlResult(id=1, task_id=1, channel=InsightCrawlerChannel.BOCHA,
        source_url="https://example.com/article", crawl_metadata={"fulltext_fetch": {"status": "failed"}})
    db = AsyncMock()
    db.add = lambda item: None
    db.exec.return_value = SimpleNamespace(all=lambda: [(result, task)])
    monkeypatch.setattr(insight_crawl_service, "enrich_discovered_result", AsyncMock(return_value=result))
    create = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "_create_candidates_from_hits", create)
    counts = await service.retry_recent_fulltext(db, user_id=1)
    assert counts["attempted"] == 1
    request = create.await_args.args[2]
    assert (request.published_start, request.published_end) == (start, end)
    assert request.enrich_fulltext_before_review is False
    result.crawl_metadata = {"fulltext_fetch": {"status": "failed"}, "fulltext_retry": {"attempts": 2}}
    counts = await service.retry_recent_fulltext(db, user_id=1)
    assert counts["attempted"] == 0
