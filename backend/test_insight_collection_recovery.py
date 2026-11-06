from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.agent.insight import InsightCompany, InsightCrawlResult, InsightMonitorConfig, InsightTask
from app.schemas.agent.insight.feishu import InsightFeishuSyncRequest
from app.services.agent.insight.crawler.search_service import insight_search_discovery_service
from app.services.agent.insight.crawler import search_service as search_module
from app.services.agent.insight.feishu_bitable_service import InsightFeishuBitableService
from app.services.agent.insight import feishu_bitable_service as sync_module
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService


def test_company_declared_abbreviation_and_aliases():
    service = InsightMonitorExecutionService()
    row = InsightMonitorConfig(id=1, object_type="company", object_name="Archer-Daniels-Midland Company")
    company = InsightCompany(name=row.object_name, short_name="Archer Daniels Midland (ADM)— 美国")
    enriched = service._with_company_aliases(row, company)
    hit = SimpleNamespace(title="ADM财报及食品配料业务进展", snippet="", url="https://example.com/1")
    assert 1 in service._assign_grouped_hits([enriched], [hit])
    assert "美国" not in service._monitor_match_terms(enriched)
    hit.title = "admin 用户管理"
    assert service._assign_grouped_hits([enriched], [hit]) == {}
    company.profile_json = {"aliases": "金龙鱼"}
    hit.title = "金龙鱼研发投入进展"
    assert 1 in service._assign_grouped_hits([service._with_company_aliases(row, company)], [hit])
    assert row.config_json is None


def intelligence(number, created, updated=None):
    return SimpleNamespace(id=number, create_time=created, update_time=updated,
                           publish_time=datetime(2025, 1, 1))


def test_incremental_sync_reconciles_old_publications_and_late_commits():
    service = InsightFeishuBitableService()
    now = datetime(2026, 11, 6, 12)
    old = now - timedelta(days=30)
    rows = [intelligence(1, old), intelligence(2, now), intelligence(3, old, now),
            intelligence(4, old), intelligence(5, old)]
    remote = [{"fields": {"情报ID": str(i), "同步时间": int((now - timedelta(hours=1)).timestamp()*1000)}}
              for i in (2, 3, 4)]
    remote.append({"fields": {"情报ID": [{"text": "5"}], "同步时间": "损坏值"}})
    # 1 即使创建时间很旧，只要远端缺失也补；2/3 是新增或修改；4 不重复写；5 保守重试。
    assert [row.id for row in service._select_incremental_rows(rows, remote)] == [1, 2, 3, 5]


@pytest.mark.asyncio
async def test_sync_reads_all_pages_and_keeps_manual_publication_filter():
    service = InsightFeishuBitableService()
    rows = [intelligence(i, datetime(2026, 11, 6)) for i in range(1, 2102)]
    db = AsyncMock()
    pages = [rows[i:i+500] for i in range(0, len(rows), 500)] + [[]]
    db.exec.side_effect = [SimpleNamespace(all=lambda page=page: page) for page in pages]
    payload = InsightFeishuSyncRequest(date_from=datetime(2026, 11, 1), date_to=datetime(2026, 11, 6))
    result = await service._load_intelligences(db, payload, user_id=1, is_admin=True)
    assert len(result) == 2101
    assert "publish_time >=" in str(db.exec.await_args_list[0].args[0])
    db.exec.side_effect = [SimpleNamespace(all=lambda: [])]
    await service._load_intelligences(db, payload, user_id=1, is_admin=True, all_active=True)
    sql = str(db.exec.await_args.args[0]).split("WHERE")[1]
    assert "publish_time" not in sql


@pytest.mark.asyncio
async def test_non_admin_sync_still_filters_visible_ids(monkeypatch):
    from app.services.agent.insight.intelligence_service import insight_intelligence_service
    monkeypatch.setattr(insight_intelligence_service, "_get_visible_intelligence_ids", AsyncMock(return_value=[]))
    db = AsyncMock()
    result = await InsightFeishuBitableService()._load_intelligences(
        db, InsightFeishuSyncRequest(scope="selected", intelligence_ids=[123]), user_id=2, is_admin=False,
    )
    assert result == []
    db.exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_lock_always_released_and_non_admin_cannot_reconcile(monkeypatch):
    service = InsightFeishuBitableService()
    db = AsyncMock()
    connection = AsyncMock()
    connection.execute.return_value = SimpleNamespace(scalar=lambda: True)
    context = AsyncMock()
    context.__aenter__.return_value = connection
    monkeypatch.setattr(sync_module, "engine", SimpleNamespace(connect=lambda: context))
    monkeypatch.setattr(service, "_sync_intelligences", AsyncMock(side_effect=RuntimeError("模拟写入失败")))
    payload = InsightFeishuSyncRequest(scope="selected", intelligence_ids=[1])
    with pytest.raises(RuntimeError):
        await service.sync_intelligences(db, payload, user_id=1, is_admin=True)
    assert "pg_advisory_unlock" in str(connection.execute.await_args.args[0])
    with pytest.raises(ValueError, match="管理员"):
        await service.sync_intelligences(db, payload, user_id=1, is_admin=False, _incremental=True)


@pytest.mark.asyncio
async def test_fulltext_failure_does_not_stop_next_record(monkeypatch):
    now = datetime.now()
    results = [InsightCrawlResult(id=i, task_id=i, source_url=f"https://example.com/{i}",
                crawl_metadata={"fulltext_fetch": {"status": "failed"}}) for i in (1, 2)]
    tasks = [InsightTask(id=i, create_time=now-timedelta(days=1), input_payload={"query": "糖浆", "freshness": "3d"})
             for i in (1, 2)]
    db = AsyncMock()
    db.add = Mock()
    db.exec.side_effect = [SimpleNamespace(all=lambda: [1, 2]),
                          *[SimpleNamespace(first=lambda pair=pair: pair) for pair in zip(results, tasks)]]
    async def enrich(session, row):
        if row.id == 1:
            raise ValueError("正文不足200字")
        row.markdown_content = "项目投产，新增糖浆产线，披露产能和工艺。" * 30
    monkeypatch.setattr(search_module.insight_crawl_service, "enrich_discovered_result", enrich)
    monkeypatch.setattr(search_module.insight_crawl_service, "mark_fulltext_failure", AsyncMock())
    create = AsyncMock(return_value=[])
    monkeypatch.setattr(insight_search_discovery_service, "_create_candidates_from_hits", create)
    counts = await insight_search_discovery_service.retry_recent_fulltext(db, user_id=1, limit=2)
    assert counts == {"attempted": 2, "success": 1, "failed": 1, "candidates": 0}
    assert str(db.exec.await_args_list[0].args[0]).startswith("SELECT insight_crawl_result.id ")
    assert db.exec.await_args_list[2].args[0].get_execution_options()["populate_existing"]
    db.rollback.assert_awaited_once()
    request = create.await_args.args[2]
    assert request.published_end == tasks[1].create_time
    assert abs((request.published_start - (tasks[1].create_time-timedelta(days=3))).total_seconds()) < 1
