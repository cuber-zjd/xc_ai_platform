from datetime import datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from app.models.agent.insight import InsightCrawlerChannel, InsightCrawlResult
from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest
from app.services.agent.insight.ai_review_service import insight_ai_review_service
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner
from app.services.agent.insight.crawler.firecrawl_client import firecrawl_client
from app.services.agent.insight.crawler.search_service import (
    insight_search_discovery_service,
)


def _crawl_result(*, published_at: datetime | None, verified: bool) -> InsightCrawlResult:
    return InsightCrawlResult(
        task_id=1,
        channel=InsightCrawlerChannel.BAIDU,
        source_url="https://example.com/article",
        source_title="测试文章",
        published_at=published_at,
        crawl_metadata={
            "publication_time": {
                "value": published_at.isoformat() if published_at else None,
                "source": "metadata" if verified else "search_result",
                "verified": verified,
            }
        },
    )


def test_publish_time_from_url_has_strong_provenance() -> None:
    published_at, source = insight_content_cleaner.parse_publish_time_with_source(
        {"url": "https://example.com/news/2026-07-29/article.html"}
    )

    assert published_at == datetime(2026, 7, 29)
    assert source == "url"


def test_body_date_is_only_weak_provenance() -> None:
    published_at, source = insight_content_cleaner.parse_publish_time_with_source(
        {},
        "这里是很长的正文内容，文章回顾了2025年9月24日发生的行业事件。",
    )

    assert published_at == datetime(2025, 9, 24)
    assert source == "content_header"


def test_page_metadata_extracts_visible_article_time() -> None:
    soup = BeautifulSoup(
        '<html><head><title>界面新闻</title></head><body>'
        '<div class="article-info"><span class="info-s">2025/09/24 17:49</span></div>'
        '</body></html>',
        "lxml",
    )

    metadata = firecrawl_client._extract_page_metadata(
        soup,
        "https://www.jiemian.com/article/13396219.html",
    )

    assert metadata["publishedTime"] == "2025/09/24 17:49"


def test_visible_article_time_wins_over_dynamic_seo_time() -> None:
    soup = BeautifulSoup(
        '<html><head><meta property="article:published_time" '
        'content="2026-08-01T10:27:04+08:00"></head><body>'
        '<div class="article-title-icon"><span class="item-time">'
        '<i>·</i>2026年07月28日 16:31</span></div></body></html>',
        "lxml",
    )

    metadata = firecrawl_client._extract_page_metadata(
        soup,
        "https://www.36kr.com/p/3914968387638920",
    )

    assert metadata["publishedTime"].endswith("2026年07月28日 16:31")


def test_direct_http_decoder_supports_gbk_html() -> None:
    html = (
        '<html><head><meta charset="gb2312"><title>净利下跌38%</title></head>'
        '<body>中国旺旺</body></html>'
    )
    response = httpx.Response(200, content=html.encode("gb18030"))

    decoded = firecrawl_client._decode_response_text(response)

    assert "净利下跌38%" in decoded
    assert "中国旺旺" in decoded


def test_daily_window_rejects_old_or_unverified_publish_time() -> None:
    request = InsightSearchDiscoveryRequest(query="功能糖", freshness="3d")
    old = _crawl_result(published_at=datetime.now() - timedelta(days=10), verified=True)
    unknown = _crawl_result(published_at=None, verified=False)
    recent = _crawl_result(published_at=datetime.now() - timedelta(days=1), verified=True)

    assert not insight_search_discovery_service._result_matches_time_window(old, request)
    assert not insight_search_discovery_service._result_matches_time_window(unknown, request)
    assert insight_search_discovery_service._result_matches_time_window(recent, request)


def test_ai_review_requires_verified_publish_time() -> None:
    search_time = _crawl_result(published_at=datetime.now(), verified=False)
    page_time = _crawl_result(published_at=datetime.now(), verified=True)

    assert not insight_ai_review_service._has_verified_publish_time(search_time)
    assert insight_ai_review_service._has_verified_publish_time(page_time)
