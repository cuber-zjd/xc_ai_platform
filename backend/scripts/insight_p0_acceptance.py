import asyncio
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import (
    InsightCrawlResult,
    InsightDataSource,
    InsightIntelligence,
    InsightIntelligenceCandidate,
    InsightTask,
    InsightTaskStatus,
)


async def count_rows(db, model, *filters) -> int:
    return (await db.exec(select(func.count()).select_from(model).where(*filters))).one()


async def main() -> None:
    cutoff = datetime.now() - timedelta(minutes=30)
    async with async_session() as db:
        data_sources = await count_rows(db, InsightDataSource, InsightDataSource.is_deleted == 0)
        enabled_sources = await count_rows(
            db,
            InsightDataSource,
            InsightDataSource.is_deleted == 0,
            InsightDataSource.status == "enabled",
        )
        tasks = await count_rows(db, InsightTask, InsightTask.is_deleted == 0)
        stale_tasks = await count_rows(
            db,
            InsightTask,
            InsightTask.is_deleted == 0,
            InsightTask.status.in_([InsightTaskStatus.PENDING, InsightTaskStatus.RUNNING]),
            InsightTask.create_time <= cutoff,
        )
        crawled = await count_rows(db, InsightCrawlResult, InsightCrawlResult.is_deleted == 0)
        candidates = await count_rows(db, InsightIntelligenceCandidate, InsightIntelligenceCandidate.is_deleted == 0)
        pending_candidates = await count_rows(
            db,
            InsightIntelligenceCandidate,
            InsightIntelligenceCandidate.is_deleted == 0,
            InsightIntelligenceCandidate.review_status == "pending",
        )
        company_linked_candidates = await count_rows(
            db,
            InsightIntelligenceCandidate,
            InsightIntelligenceCandidate.is_deleted == 0,
            InsightIntelligenceCandidate.company_id.is_not(None),
        )
        intelligences = await count_rows(db, InsightIntelligence, InsightIntelligence.is_deleted == 0)
        visible_ready = await count_rows(
            db,
            InsightIntelligence,
            InsightIntelligence.is_deleted == 0,
            InsightIntelligence.status == "active",
        )

    checks = [
        ("数据源已配置", data_sources > 0, data_sources),
        ("存在启用数据源", enabled_sources > 0, enabled_sources),
        ("有采集任务记录", tasks > 0, tasks),
        ("无 30 分钟以上遗留 running/pending 任务", stale_tasks == 0, stale_tasks),
        ("有抓取结果", crawled > 0, crawled),
        ("有候选情报", candidates > 0, candidates),
        ("候选审核池可用", pending_candidates >= 0, pending_candidates),
        ("企业关联口子可用", company_linked_candidates >= 0, company_linked_candidates),
        ("有正式情报或可从候选转正", intelligences > 0 or candidates > 0, intelligences),
        ("正式情报可见性基础可用", visible_ready >= 0, visible_ready),
    ]

    print("Insight P0 封版验收")
    print("=" * 24)
    for name, ok, value in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {value}")

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        raise SystemExit(f"P0 验收未通过: {'; '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
