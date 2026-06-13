import asyncio
import re

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightCrawlResult, InsightIntelligence, InsightIntelligenceCandidate, InsightIntelligenceSource
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


TYPE_MAP = {
    "strategic_planning": "战略规划",
    "strategy": "战略规划",
    "marketing_strategy": "营销策略",
    "competitor_strategy": "竞品动态",
    "competitor": "竞品动态",
    "product_launch": "新品情报",
    "product_launch_failure": "新品情报",
    "new_product": "新品情报",
    "financial_report": "财报公告",
    "financial": "财报公告",
    "industry_news": "行业资讯",
    "industry": "行业资讯",
    "policy": "政策法规",
    "regulation": "政策法规",
    "application_solution": "应用方案",
    "technology": "应用方案",
    "business_operation": "经营动态",
    "operation": "经营动态",
    "risk_warning": "风险预警",
    "risk": "风险预警",
    "csr/esg": "企业社会责任/ESG",
    "corporate_social_responsibility": "企业社会责任",
    "corporate_strategy_&_esg": "战略规划",
    "market_analysis": "市场分析",
    "market_expansion": "市场扩张",
    "market_trend": "市场趋势",
}


async def main() -> None:
    async with async_session() as db:
        fixed_types = 0
        fixed_times = 0

        crawl_results = list((await db.exec(select(InsightCrawlResult).where(InsightCrawlResult.is_deleted == 0))).all())
        for row in crawl_results:
            parsed = row.published_at or parse_time(
                row.crawl_metadata,
                row.source_title,
                row.snippet,
                row.markdown_content,
            )
            if parsed and not row.published_at:
                row.published_at = parsed
                fixed_times += 1

        candidates = list((await db.exec(select(InsightIntelligenceCandidate).where(InsightIntelligenceCandidate.is_deleted == 0))).all())
        for row in candidates:
            normalized = normalize_type(row.intelligence_type)
            if normalized != row.intelligence_type:
                row.intelligence_type = normalized
                fixed_types += 1

        sources = list((await db.exec(select(InsightIntelligenceSource).where(InsightIntelligenceSource.is_deleted == 0))).all())
        source_by_intelligence: dict[int, list[InsightIntelligenceSource]] = {}
        for source in sources:
            parsed = source.source_publish_time or parse_time(
                source.source_metadata,
                source.source_title,
                source.content_excerpt,
            )
            if parsed and not source.source_publish_time:
                source.source_publish_time = parsed
                fixed_times += 1
            source_by_intelligence.setdefault(source.intelligence_id, []).append(source)

        intelligences = list((await db.exec(select(InsightIntelligence).where(InsightIntelligence.is_deleted == 0))).all())
        for row in intelligences:
            normalized = normalize_type(row.intelligence_type)
            if normalized != row.intelligence_type:
                row.intelligence_type = normalized
                fixed_types += 1
            parsed = row.publish_time or next(
                (source.source_publish_time for source in source_by_intelligence.get(row.id or 0, []) if source.source_publish_time),
                None,
            )
            parsed = parsed or parse_time(row.raw_payload, row.title, row.summary, row.content)
            if parsed and not row.publish_time:
                row.publish_time = parsed
                fixed_times += 1

        await db.commit()
        print({"fixed_types": fixed_types, "fixed_times": fixed_times})


def normalize_type(value: object) -> str:
    text = str(value or "").strip()
    normalized = text.lower().replace("-", "_").replace(" ", "_")
    if normalized in TYPE_MAP:
        return TYPE_MAP[normalized]
    if re.fullmatch(r"[A-Za-z0-9_]+", text):
        return "行业资讯"
    return text[:50] if text else "行业资讯"


def parse_time(*values: object):
    metadata = next((value for value in values if isinstance(value, dict)), {})
    texts = [value for value in values if isinstance(value, str)]
    if isinstance(metadata, dict):
        nested = metadata.get("metadata")
        if isinstance(nested, dict):
            metadata = metadata | nested
        raw = metadata.get("raw")
        if isinstance(raw, dict):
            metadata = metadata | raw
        search_context = metadata.get("search_context")
        if isinstance(search_context, str):
            texts.append(search_context)
    return insight_content_cleaner.parse_publish_time(metadata, *texts)


if __name__ == "__main__":
    asyncio.run(main())
