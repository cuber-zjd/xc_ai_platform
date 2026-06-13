"""刷新已入库候选情报摘要，清理 markdown 链接、导航和安全验证噪声。"""

from __future__ import annotations

import asyncio

from sqlmodel import select

from app.db.session import async_session, engine
from app.models.agent.insight import InsightCrawlResult, InsightIntelligenceCandidate
from app.services.agent.insight.crawler.content_cleaner import insight_content_cleaner


async def main() -> None:
    engine.echo = False
    updated_candidates = 0
    updated_crawls = 0
    async with async_session() as session:
        statement = select(InsightIntelligenceCandidate, InsightCrawlResult).join(
            InsightCrawlResult,
            InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id,
        )
        rows = (await session.exec(statement)).all()
        for candidate, crawl_result in rows:
            source_text = crawl_result.markdown_content or crawl_result.snippet or candidate.candidate_summary
            cleaned = insight_content_cleaner.clean_summary(source_text, 500)
            if cleaned and cleaned != candidate.candidate_summary:
                candidate.candidate_summary = cleaned
                updated_candidates += 1
            if cleaned and cleaned != crawl_result.snippet:
                crawl_result.snippet = cleaned
                updated_crawls += 1
        await session.commit()
    print(f"候选摘要刷新完成：候选 {updated_candidates} 条，采集摘要 {updated_crawls} 条")


if __name__ == "__main__":
    asyncio.run(main())
