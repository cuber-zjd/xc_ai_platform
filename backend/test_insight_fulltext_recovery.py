import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.models.agent.insight import InsightCrawlResult, InsightTask
from app.services.agent.insight.crawler.firecrawl_client import FirecrawlClient, FulltextAccessBlocked
from app.services.agent.insight.crawler import search_service as search_module
from app.services.agent.insight.feishu_bitable_service import InsightFeishuBitableService


@pytest.mark.parametrize("url", [
    "https://sou.toutiao.com/search/jump?url=http://www.toutiao.com/a7704993510214894080/?channel=&source=search_tab",
    "https://sou.toutiao.com/search/jump?url=https%3A%2F%2Fwww.toutiao.com%2Fa7704993510214894080%2F",
    "http://www.toutiao.com/a7704993510214894080/",
])
def test_toutiao_canonical(url):
    assert FirecrawlClient.canonical_article_url(url) == "https://www.toutiao.com/article/7704993510214894080/"


@pytest.mark.parametrize("target", ["http://127.0.0.1/a123/", "http://www.toutiao.com.evil.test/a123/"])
def test_toutiao_jump_rejects_other_hosts(target):
    with pytest.raises(ValueError):
        FirecrawlClient.canonical_article_url("https://sou.toutiao.com/search/jump?url=" + target)


@pytest.mark.asyncio
async def test_blocked_site_does_not_fallback_or_repeat(monkeypatch):
    client = FirecrawlClient()
    scrape = AsyncMock(return_value={"markdown": "请完成安全验证"})
    direct = AsyncMock()
    monkeypatch.setattr(client, "scrape_url", scrape)
    monkeypatch.setattr(client, "_scrape_direct", direct)
    for _ in range(2):
        with pytest.raises(FulltextAccessBlocked):
            await client.scrape_url_with_fallback("https://www.toutiao.com/a123/")
    assert scrape.await_count == 1
    direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_toutiao_shell_is_not_article(monkeypatch):
    client = FirecrawlClient()
    monkeypatch.setattr(client, "_ensure_public_url", AsyncMock())
    response = httpx.Response(200, text="<html><body>" + "推荐新闻列表。" * 90 + "</body></html>",
                              request=httpx.Request("GET", "https://www.toutiao.com/article/123/"))
    monkeypatch.setattr(client, "_get_public_page", AsyncMock(return_value=response))
    with pytest.raises(ValueError, match="脚本外壳"):
        await client._scrape_direct(str(response.url))


def test_sync_body_repairs_old_row_and_joins_richtext():
    service = InsightFeishuBitableService()
    now = datetime.now()
    row = SimpleNamespace(id=1, create_time=now-timedelta(days=20), update_time=None, content="第一段第二段")
    remote = [{"fields": {"情报ID": "1", "同步时间": now.timestamp()*1000}}]
    assert service._select_incremental_rows([row], remote) == [row]
    remote[0]["fields"]["正文"] = [{"text": "第一段"}, {"text": "第二段"}]
    assert service._select_incremental_rows([row], remote) == []
    assert "content" in service._selected_field_codes([])
    assert "content" not in service._selected_field_codes(["title"])
    assert service._normalize_text_value([{"text": "第一段\n"}, {"text": "第二段 "}, {"text": "链接"}]) == "第一段\n第二段 链接"


@pytest.mark.asyncio
async def test_item_timeout_keeps_other_records_running(monkeypatch):
    service = search_module.insight_search_discovery_service
    db = AsyncMock()
    db.add = Mock()
    rows = [InsightCrawlResult(id=i, task_id=i, source_url=f"https://example.org/{i}") for i in (1, 2)]
    task = InsightTask(create_time=datetime.now(), input_payload={"query": "糖浆", "freshness": "3d"})
    db.exec.side_effect = [SimpleNamespace(first=lambda row=row: (row, task)) for row in rows]
    async def enrich(session, row):
        if row.id == 1:
            await asyncio.sleep(5)
        row.markdown_content = "糖浆工艺研发项目已建成投产。" * 50
    monkeypatch.setattr(search_module.settings, "INSIGHT_FULLTEXT_RETRY_FETCH_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(search_module.insight_crawl_service, "enrich_discovered_result", enrich)
    failure = AsyncMock()
    monkeypatch.setattr(search_module.insight_crawl_service, "mark_fulltext_failure", failure)
    monkeypatch.setattr(service, "_create_candidates_from_hits", AsyncMock(return_value=[]))
    monkeypatch.setattr(search_module.insight_crawl_service, "backfill_promoted_fulltext", AsyncMock(return_value=[]))
    result = await service._retry_fulltext_records(db, user_id=1, result_ids=[1, 2], repair=True)
    assert result["attempted"] == 2
    assert result["success"] == 1
    assert result["failed"] == 1
    assert "TimeoutError" in failure.await_args.args[2]


@pytest.mark.asyncio
async def test_review_failure_keeps_body_for_later_review(monkeypatch):
    service = search_module.insight_search_discovery_service
    row = InsightCrawlResult(id=1, task_id=1, source_url="https://example.org/1")
    task = InsightTask(create_time=datetime.now(), input_payload={"query": "糖浆"})
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(first=lambda: (row, task))
    async def enrich(*args):
        row.markdown_content = "糖浆工艺研发项目已建成投产。" * 50
    monkeypatch.setattr(search_module.insight_crawl_service, "enrich_discovered_result", enrich)
    monkeypatch.setattr(service, "_create_candidates_from_hits", AsyncMock(side_effect=TimeoutError()))
    failure = AsyncMock()
    monkeypatch.setattr(search_module.insight_crawl_service, "mark_fulltext_failure", failure)
    await service._retry_fulltext_records(db, user_id=1, result_ids=[1], repair=True)
    assert row.crawl_metadata["fulltext_retry"]["status"] == "review_pending"
    assert len(row.markdown_content) > 200
    failure.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0, 0.000000001])
async def test_batch_checkpoints_and_soft_budget(monkeypatch, budget):
    from app.services.agent.insight.crawler import fulltext_retry_service as module
    from itertools import count
    ticks = count()
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    rows = [InsightCrawlResult(id=i, source_url=f"https://{host}.example.org/{i}",
                              create_time=datetime.now()) for i, host in [(1, "a"), (2, "a"), (3, "b")]]
    objects = {row.id: row for row in rows}
    audit = None
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(all=lambda: rows)
    async def refresh(task):
        nonlocal audit
        task.id = 999
        audit = task
    db.refresh.side_effect = refresh
    context_db = AsyncMock()
    context_db.add = Mock()
    async def get(kind, number, **kwargs):
        return audit if kind is InsightTask else objects[number]
    context_db.get.side_effect = get
    context = AsyncMock()
    context.__aenter__.return_value = context_db
    monkeypatch.setattr(module, "async_session", lambda: context)
    running = set()
    async def retry(session, *, result_ids, **kwargs):
        # refresh 开启的事务必须已释放，避免上线时 DDL 被长批次阻塞。
        assert db.commit.await_count == 2
        row = objects[result_ids[0]]
        host = row.source_url.split("/")[2]
        assert host not in running
        running.add(host)
        await asyncio.sleep(0.01)
        running.remove(host)
        row.markdown_content = "糖浆生产项目扩建完成。" * 40
        row.crawl_metadata = {"fulltext_retry": {"status": "success"}, "fulltext_fetch": {"provider": "firecrawl"}}
        return {"attempted": 1, "candidates": 0}
    call = AsyncMock(side_effect=retry)
    monkeypatch.setattr(search_module.insight_search_discovery_service, "_retry_fulltext_records", call)
    result = await module.fulltext_retry_service._run(db, user_id=1, limit=0, days=7, repair=True, budget_seconds=budget)
    assert result["selected"] == 3
    assert result["remaining"] == 0
    assert len(audit.output_payload["items"]) == 3
    assert result["success"] == (3 if budget == 0 else 0)
    assert result["deferred"] == (0 if budget == 0 else 3)
    assert call.await_count == (3 if budget == 0 else 0)


@pytest.mark.asyncio
async def test_toutiao_body_excludes_app_and_recommendation(monkeypatch):
    client = FirecrawlClient()
    body = "项目已正式投产，披露新增生产线与原料采购计划。" * 20
    html = f"<html><h1>项目投产</h1><div>打开APP</div><article>{body}</article><aside>推荐新闻</aside></html>"
    raw = html.replace("<html>", '<html><script type="application/ld+json">'
                       '{"@type":"NewsArticle","datePublished":"2026-11-06T17:50:09+08:00",'
                       '"dateModified":"2026-11-07T09:00:43+08:00"}</script>')
    monkeypatch.setattr(client, "scrape_url", AsyncMock(return_value={"rawHtml": raw, "html": html, "markdown": "导航" + body}))
    result = await client._scrape_with_fallback("https://www.toutiao.com/article/123/")
    assert result["markdown"] == body
    assert result["metadata"]["title"] == "项目投产"
    assert result["metadata"]["publishedTime"] == "2026-11-06T17:50:09+08:00"


@pytest.mark.asyncio
async def test_formal_body_backfill_preserves_business_fields(monkeypatch):
    from app.models.agent.insight import InsightIntelligence
    from app.services.agent.insight.asset_service import insight_asset_service
    from app.services.agent.insight.crawler.crawl_service import insight_crawl_service
    row = InsightIntelligence(id=20, title="原有情报", content=None, company_id=9,
                              publish_time=datetime(2026, 11, 1), raw_payload={"crawl_result_id": 10})
    crawl = InsightCrawlResult(id=10, source_url="https://example.org/news/10",
                               markdown_content="糖浆生产项目扩建完成，新增采购计划。" * 30)
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(all=lambda: [row])
    index = AsyncMock()
    monkeypatch.setattr(insight_asset_service, "upsert_intelligence_asset", index)
    assert await insight_crawl_service.backfill_promoted_fulltext(db, crawl) == [20]
    sql = str(db.exec.await_args.args[0])
    assert "content IS NULL" in sql and "FOR UPDATE" in sql and "raw_payload" in sql
    assert row.content == crawl.markdown_content
    assert row.title == "原有情报" and row.company_id == 9 and row.publish_time == datetime(2026, 11, 1)
    index.assert_awaited_once()
