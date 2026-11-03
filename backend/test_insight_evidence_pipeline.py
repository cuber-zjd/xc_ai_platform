import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.llm_factory import LLMFactory
from app.models.agent.insight import InsightChannel, InsightMonitorConfig
from app.services.agent.insight.company_context import insight_company_material_rejection_reason
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client
from app.services.agent.insight.crawler.search_client import DoubaoWebSearchClient
from app.services.agent.insight.feishu_brief_service import InsightFeishuBriefService
from app.services.agent.insight.feishu_monthly_report_service import InsightFeishuMonthlyReportService
from app.services.agent.insight.monitor_execution_service import InsightMonitorExecutionService
from app.services.agent.insight import monitor_execution_service as monitor_module
from app.services.agent.insight.report_evidence import MaterialApprovalIncomplete, citation_coverage, evidence_excerpt, report_material_context, report_model_names, report_policy_snapshot
from app.schemas.agent.insight.feishu_brief import InsightFeishuBriefGenerationRules


def test_empty_answer_does_not_promote_unselected_citations():
    context = {"annotations": [{"url": "https://example.com/home", "title": "官网"}]}
    assert DoubaoWebSearchClient()._parse_answer('{"items":[]}', context, 10) == []


def test_unlimited_search_does_not_silently_use_fifteen_days():
    assert "不限时间" in DoubaoWebSearchClient()._build_prompt("公告", 10, "noLimit")


def test_navigation_shell_is_not_article():
    content = "正在加载，请稍候。\n" + "相关新闻推荐新闻栏目客户端下载" * 30
    assert insight_content_cleaner.fulltext_error(content)
    assert insight_content_cleaner.fulltext_error("项目本月投产，披露产能及工艺数据。" * 30) is None


def test_date_conflict_remains_unverified():
    soup = BeautifulSoup('<meta property="article:published_time" content="2026-01-09"><article><time datetime="2026-11-01">发布时间</time></article>', "lxml")
    metadata = firecrawl_client._extract_page_metadata(soup, "https://example.com/news")
    assert metadata["publication_conflict"]
    assert len(metadata["publication_evidence"]) == 2
    assert insight_content_cleaner.parse_publish_time_with_source(metadata) == (None, "conflict")


def test_roquette_english_header_conflict_is_not_silently_overwritten():
    soup = BeautifulSoup('<meta property="article:published_time" content="2026-01-09"><article>Published November 1, 2026 技术信息</article>', "lxml")
    metadata = firecrawl_client._extract_page_metadata(soup, "https://www.roquette.com/food-nutrition/resources/test")
    assert metadata["publication_conflict"]


def test_foodmate_mobile_uses_publication_header_not_event_or_recommendation():
    soup = BeautifulSoup('<div class="info">日期: 2026-10-09 来源: 浙里好市监微信号</div><div>活动将在2026-10-17举办</div><div class="tjxw">推荐新闻 2026-10-08</div>', "lxml")
    metadata = firecrawl_client._extract_page_metadata(soup, "https://news.foodmate.net/wap/index.php?moduleid=21&itemid=754413")
    value, source = insight_content_cleaner.parse_publish_time_with_source(metadata)
    assert value == datetime(2026, 10, 9)
    assert source == "metadata"
    assert metadata["publication_evidence"][0]["location"] == "foodmate wap div.info 日期"


def test_search_and_ai_review_share_fulltext_gate():
    from app.models.agent.insight import InsightCrawlResult
    from app.services.agent.insight.ai_review_service import insight_ai_review_service
    from app.services.agent.insight.crawler.search_service import insight_search_discovery_service
    row = InsightCrawlResult(task_id=1, source_url="https://example.com/1", markdown_content="正在加载" + "导航信息" * 80)
    assert not insight_search_discovery_service._has_fulltext(row)
    assert not insight_ai_review_service._has_sufficient_fulltext(row)


def test_related_jsonld_date_is_not_article_date():
    assert firecrawl_client._find_json_date({"related": {"datePublished": "2026-11-01"}}) is None


def test_publication_timezone_does_not_depend_on_server_timezone():
    value, source = insight_content_cleaner.parse_publish_time_with_source({"publishedTime": "2026-10-31T18:00:00Z"})
    assert value == datetime(2026, 11, 1, 2)
    assert source == "metadata"


def test_confirmed_alias_matches_accents_without_matching_other_words():
    service = InsightMonitorExecutionService()
    row = InsightMonitorConfig(id=1, config_code="test", config_name="罗盖特监测", object_type="company", object_name="Roquette Frères", config_json={"aliases": ["Roquette"]})
    hit = SimpleNamespace(title="ROQUETTE 新产线", snippet="", url="https://example.com/1")
    assert 1 in service._assign_grouped_hits([row], [hit])
    assert service._term_matches("Roquette Frères", service._normalize_match_text("Roquette Freres 新产线"))
    assert not service._term_matches("ADM", service._normalize_match_text("admin 新闻"))


def test_unknown_hit_does_not_get_assigned_to_first_three_topics():
    row = InsightMonitorConfig(id=1, config_code="test", config_name="糖浆监测", object_name="糖浆")
    hit = SimpleNamespace(title="无关新闻", snippet="", url="https://example.com/1")
    assert InsightMonitorExecutionService()._assign_grouped_hits([row], [hit]) == {}


def test_evidence_keeps_tail_and_original_offsets():
    body = "开头介绍" * 600 + "\n" + "正文数据" * 600 + "\n项目已投产，产能12万吨。"
    excerpt = evidence_excerpt(body, budget=900)
    assert not excerpt["complete"]
    assert "产能12万吨" in excerpt["text"]
    assert excerpt["source_chars"] == len(body)
    assert sum(end - start for start, end in excerpt["spans"]) <= 900


def test_context_budget_counts_encoded_metadata_without_dropping_events(monkeypatch):
    monkeypatch.setattr(settings, "INSIGHT_REPORT_CONTEXT_CHAR_BUDGET", 10000)
    materials = [{"id": value, "title": "项目投产", "content": "披露产能12万吨。" * 1000, "summary": "事件概览" * 150} for value in range(12)]
    context = report_material_context(materials)
    assert [item["id"] for item in context] == list(range(12))
    assert len(json.dumps(context, ensure_ascii=False, default=str)) <= 10000
    assert all(item["original_evidence"]["text"] for item in context)


def test_context_fails_explicitly_if_all_indexes_cannot_fit(monkeypatch):
    monkeypatch.setattr(settings, "INSIGHT_REPORT_CONTEXT_CHAR_BUDGET", 10000)
    with pytest.raises(ValueError, match="未截断候选材料"):
        report_material_context([{"id": index, "title": "标题" * 400} for index in range(100)])


def test_model_roles_and_policy_snapshot_are_explicit(monkeypatch):
    monkeypatch.setattr(settings, "INSIGHT_REPORT_WRITER_MODELS", " writer-a,writer-b,writer-a ")
    monkeypatch.setattr(settings, "INSIGHT_REPORT_REVIEWER_MODELS", "reviewer-c")
    assert report_model_names("writer") == ["writer-a", "writer-b"]
    snapshot = report_policy_snapshot()
    assert snapshot["preferred_models"]["reviewer"] == ["reviewer-c"]
    assert snapshot["material_quota"] is None


@pytest.mark.asyncio
async def test_direct_fetch_checks_every_redirect(monkeypatch):
    visited = []

    async def validate(url):
        visited.append(url)
        if "127.0.0.1" in url:
            raise ValueError("禁止直接抓取内网地址")

    monkeypatch.setattr(firecrawl_client, "_ensure_public_url", validate)
    transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "http://127.0.0.1/private"}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="内网"):
            await firecrawl_client._get_public_page(client, "https://example.com/page")
    assert visited == ["https://example.com/page", "http://127.0.0.1/private"]


@pytest.mark.asyncio
async def test_direct_fetch_enforces_streamed_body_limit(monkeypatch):
    monkeypatch.setattr(firecrawl_client, "_ensure_public_url", AsyncMock())

    class LargeBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(6):
                yield b"a" * (1024 * 1024)
            pytest.fail("达到上限后不应继续消费响应")

    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=LargeBody(), headers={"content-type": "text/html"}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError, match="5MB"):
            await firecrawl_client._get_public_page(client, "https://example.com/page")


def test_citation_coverage_keeps_uncited_items_and_normalizes_tracking():
    materials = [{"id": 1, "source_url": "https://example.com/1"}, {"id": 2, "source_url": "https://example.com/2"}]
    audit = citation_coverage("## 技术\n[项目投产](https://example.com/1?utm_source=test)", materials)
    assert audit["cited_count"] == 1
    assert audit["items"][0]["sections"] == ["技术"]
    assert audit["items"][1]["status"] == "not_cited"


def test_company_boundaries_do_not_treat_interest_as_product():
    assert insight_company_material_rejection_reason("健源", {"title": "甜蛋白获批新型甜味剂"}) is None
    assert insight_company_material_rejection_reason("健源", {"title": "禹王大豆蛋白扩产", "summary": "食品行业新品"})
    assert insight_company_material_rejection_reason("御馨", {"title": "豆粕期货上涨", "summary": "饲料供应充足"})


@pytest.mark.asyncio
async def test_monthly_pending_is_not_rejected_and_foreign_ids_are_ignored(monkeypatch):
    service = InsightFeishuMonthlyReportService()
    monkeypatch.setattr(service, "_cross_company_material_reason", lambda *args: None)
    monkeypatch.setattr(service, "_invoke_json", AsyncMock(return_value=({"approved": [{"id": 1, "score": 90}, {"id": 999, "score": 99}], "rejected": [{"id": 2, "reason": "证据不足"}, {"id": 1000, "reason": "错误ID"}]}, "test")))
    materials = [{"id": value, "title": "测试"} for value in range(1, 4)]
    selected, audit = await service._approve_materials(company_name="健源", period_start=datetime(2026, 10, 1), period_end=datetime(2026, 11, 1), materials=materials, model_names=["test"], stage_trace=[])
    assert [item["id"] for item in selected] == [1]
    assert audit["rejected_count"] == audit["pending_count"] == 1
    assert audit["candidate_count"] == audit["approved_count"] + audit["rejected_count"] + audit["pending_count"]


@pytest.mark.asyncio
async def test_weekly_approval_failure_cannot_bypass_review(monkeypatch):
    monkeypatch.setattr(LLMFactory, "safe_invoke", AsyncMock(side_effect=TimeoutError()))
    with pytest.raises(MaterialApprovalIncomplete) as error:
        await InsightFeishuBriefService()._select_materials(company_name="健源", period_start=datetime(2026, 10, 1), period_end=datetime(2026, 11, 1), materials=[{"id": 1, "title": "糖浆产线投产"}], generation_rules=InsightFeishuBriefGenerationRules())
    assert error.value.audit["pending_count"] == 1
    assert error.value.audit["selected_count"] == 0


@pytest.mark.asyncio
async def test_monthly_approval_concurrency_is_bounded(monkeypatch):
    service = InsightFeishuMonthlyReportService()
    monkeypatch.setattr(settings, "INSIGHT_REPORT_APPROVAL_CONCURRENCY", 2)
    monkeypatch.setattr(service, "_cross_company_material_reason", lambda *args: None)
    active = maximum = 0

    async def invoke(**kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"approved": [], "rejected": []}, "test"

    monkeypatch.setattr(service, "_invoke_json", invoke)
    _, audit = await service._approve_materials(company_name="健源", period_start=datetime(2026, 10, 1), period_end=datetime(2026, 11, 1), materials=[{"id": index} for index in range(1, 261)], model_names=["test"], stage_trace=[])
    assert maximum == 2
    assert audit["pending_count"] == 260


@pytest.mark.asyncio
async def test_gap_search_is_bounded_and_ingests_with_original_monitor(monkeypatch):
    service = InsightMonitorExecutionService()
    row = InsightMonitorConfig(id=1, config_code="acme", config_name="企业监测", object_type="company", object_name="Acme Holdings", config_json={"aliases": ["Acme"]})
    hit = SimpleNamespace(title="Acme 新工厂投产", snippet="植物蛋白产线", url="https://example.com/news")
    db = AsyncMock()
    db.add = Mock()
    db.exec.return_value = SimpleNamespace(all=lambda: [row])
    db.get.return_value = row
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr(monitor_module, "async_session", lambda: context)
    monkeypatch.setattr(service, "_active_channels", AsyncMock(return_value=[InsightChannel(id=1, channel_code="bocha_search", channel_name="博查")]))
    search = AsyncMock(side_effect=[[], [hit]])
    monkeypatch.setattr(service, "_search_grouped_channel", search)

    async def checkpoint(key, invoke):
        return await invoke()

    monkeypatch.setattr(monitor_module, "checkpointed_search", checkpoint)
    monkeypatch.setattr(settings, "INSIGHT_SCHEDULER_GROUPED_GAP_QUERY_LIMIT", 1)
    ingest = AsyncMock(return_value=SimpleNamespace(hits=[hit], candidates=[], task=SimpleNamespace(output_payload={})))
    monkeypatch.setattr(monitor_module.insight_search_discovery_service, "ingest_search_hits", ingest)
    result = await service._execute_grouped_daily_discovery(db, [1], user_id=7, channel_codes={"bocha_search"})
    assert search.await_count == 2
    assert ingest.await_args is not None, result
    assert ingest.await_args.args[1].monitor_config_id == 1
    assert result["batches"][0]["gap_searches"][0]["query"] == "Acme"
    assert result["batches"][0]["unmatched_monitor_ids"] == []
