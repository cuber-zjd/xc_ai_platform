import pytest

from app.models.agent.insight import (
    InsightChannel,
    InsightCrawlerChannel,
    InsightMonitorConfig,
)
from app.services.agent.insight.crawler.search_client import InsightSearchHit
from app.services.agent.insight.monitor_execution_service import (
    GroupedDiscoveryBatch,
    InsightMonitorExecutionService,
)


def _monitor(row_id: int) -> InsightMonitorConfig:
    return InsightMonitorConfig(
        id=row_id,
        config_code=f"test_{row_id}",
        config_name=f"测试企业{row_id}",
        monitor_type="enterprise",
        object_type="company",
        object_name=f"测试企业{row_id}",
        relation_type="客户",
        enabled_modules=["企业新闻"],
        keywords=[f"测试企业{row_id}"],
    )


def test_grouped_discovery_supports_independent_batch_sizes() -> None:
    service = InsightMonitorExecutionService()
    rows = [_monitor(index) for index in range(1, 10)]

    bocha_batches = service._build_grouped_discovery_batches(rows, batch_size=8)
    doubao_batches = service._build_grouped_discovery_batches(rows, batch_size=4)

    assert [len(batch.rows) for batch in bocha_batches] == [8, 1]
    assert [len(batch.rows) for batch in doubao_batches] == [4, 4, 1]


def test_daily_key_channel_prefers_matching_business_topics() -> None:
    service = InsightMonitorExecutionService()
    protein = _monitor(101)
    protein.object_type = "topic"
    protein.enabled_modules = ["行业资讯", "技术专利"]
    protein.keywords = ["植物蛋白", "大豆蛋白"]
    policy = _monitor(102)
    policy.object_type = "topic"
    policy.enabled_modules = ["政策监管"]
    policy.keywords = ["食品政策", "市场监管"]
    customer = _monitor(103)
    customer.object_type = "topic"
    customer.enabled_modules = ["企业新闻", "综合舆情"]
    customer.keywords = ["茶饮客户", "饮料新品"]
    channel = InsightChannel(
        id=23,
        channel_code="food_daily",
        channel_name="FoodDaily",
        channel_type="industry_media",
        applicable_scenarios=["行业资讯"],
        default_frequency="daily",
    )

    selected = service._select_daily_adapter_monitors(
        channel,
        [protein, policy, customer],
        2,
    )

    assert selected[0].id == protein.id
    assert len(selected) == 2
    assert service._daily_adapter_query(protein, channel) in protein.keywords


@pytest.mark.asyncio
async def test_doubao_failure_is_split_into_smaller_compensation_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = InsightMonitorExecutionService()
    rows = [_monitor(index) for index in range(1, 5)]
    batch = GroupedDiscoveryBatch(
        group_key="company:客户:企业新闻:1",
        group_name="测试客户组",
        rows=rows,
        query="测试客户组 企业新闻",
    )
    calls: list[int] = []

    async def fake_search(
        current_batch: GroupedDiscoveryBatch,
        handler_code: str,
        *,
        freshness_override: str | None = None,
    ) -> list[InsightSearchHit]:
        del handler_code, freshness_override
        calls.append(len(current_batch.rows))
        if len(calls) == 1:
            raise TimeoutError("模拟首次联网搜索超时")
        return [
            InsightSearchHit(
                channel=InsightCrawlerChannel.DOUBAO_WEB_SEARCH,
                title=current_batch.group_name,
                url=f"https://example.com/{current_batch.group_key}",
            )
        ]

    monkeypatch.setattr(
        service,
        "_search_grouped_channel",
        fake_search,
    )

    hits, metadata = await service._search_grouped_channel_with_retry(
        batch,
        "doubao_web_search",
        freshness_override="3d",
    )

    assert calls == [4, 2, 2]
    assert len(hits) == 2
    assert metadata["retry_count"] == 2
    assert metadata["retry_errors"] == []
