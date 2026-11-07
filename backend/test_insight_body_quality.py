from app.services.agent.insight.crawler.body_quality import assess_body
from unittest.mock import AsyncMock

import pytest

from app.services.agent.insight.crawler.firecrawl_client import FirecrawlClient


def test_preserves_short_factual_news():
    text = "国务院公布食品产业发展政策，涉及质量管理和产业扶持。" * 12
    cleaned, quality = assess_body(text, "国务院公布食品产业发展政策")
    assert cleaned == text
    assert quality["status"] == "passed_rules"


def test_duplicate_and_ui_preserve_original_evidence():
    paragraph = "玉米深加工企业发布新增生产线建设公告，介绍产能、生产工艺及后续采购安排。" * 5
    original = f"首页\n{paragraph}\n{paragraph}\n联系我们"
    cleaned, quality = assess_body(original, "玉米深加工生产线建设")
    assert cleaned == paragraph
    assert len(quality["removed"]) == 3
    assert quality["original_chars"] == len(original)


def test_reference_and_video_not_deleted():
    for title, body in [("谷神公司 - 企查查", "企业信息" * 100),
                        ("玉米加工项目", "打开今日头条查看完整视频\n" + "玉米加工项目" * 60)]:
        cleaned, quality = assess_body(body, title)
        assert cleaned
        assert quality["status"] == "needs_review"


def test_link_dense_and_title_mismatch_flagged():
    body = "\n".join(f"[其他资讯{i}](https://example.org/{i})" for i in range(30))
    cleaned, quality = assess_body(body, "玉米糖浆工厂正式投产")
    assert cleaned == body
    assert quality["status"] == "needs_review"
    assert len(quality["issues"]) >= 2


@pytest.mark.parametrize("footer", ["| Disclaimer |  |", "| 免責聲明 |  |", "| 網站地圖 |  |",
                                    "[股價](<javascript:gotobmp('01364')>)"])
def test_site_footer_is_retained_but_flagged(footer):
    body = "企业公布生产线投资3000万元，新增年产能2万吨。" * 15 + "\n" + footer
    cleaned, quality = assess_body(body, "企业生产线投资")
    assert cleaned == body
    assert quality["status"] == "needs_review"


def test_disclaimer_in_business_sentence_is_not_removed():
    body = "企业公告的免责声明指出，计划投资金额以最终审批为准。" * 15
    cleaned, quality = assess_body(body, "企业公告")
    assert cleaned == body
    assert quality["status"] == "passed_rules"


@pytest.mark.asyncio
async def test_html_main_text_keeps_facts_not_navigation(monkeypatch):
    client = FirecrawlClient()
    paragraphs = [f"企业第{i}条生产线于本月投产，项目投资3000万元，计划新增年产能2万吨。" * 3 for i in range(5)]
    html = '<html><head><title>企业生产线投产</title></head><body><nav>'
    html += ''.join(f'<a href="/{i}">无关导航{i}</a>' for i in range(60))
    html += '</nav><div class="story">' + ''.join(f'<p>{p}</p>' for p in paragraphs) + '</div></body></html>'
    monkeypatch.setattr(client, "scrape_url", AsyncMock(return_value={"html": html, "markdown": "无关导航" * 200}))
    result = await client._scrape_with_fallback("https://example.org/news/1")
    assert "3000万元" in result["markdown"] and "2万吨" in result["markdown"]
    assert "无关导航" not in result["markdown"]
    assert result["metadata"]["body_selector"] == "trafilatura"
