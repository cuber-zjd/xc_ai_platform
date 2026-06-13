import asyncio

from app.db.session import async_session
from app.services.agent.insight.quality_service import insight_quality_service


async def main() -> None:
    async with async_session() as db:
        overview = await insight_quality_service.get_overview(db)

    collection_keys = {metric.key for metric in overview.collection_metrics}
    review_keys = {metric.key for metric in overview.review_metrics}
    ai_keys = {metric.key for metric in overview.ai_metrics}
    source_rows_valid = all(row.total_tasks >= row.success_tasks + row.failed_tasks for row in overview.source_metrics)

    checks = {
        "采集质量指标可计算": {"task_total", "task_success_rate", "candidate_rate"}.issubset(collection_keys),
        "审核质量指标可计算": {"candidate_total", "reviewed_total", "promote_rate", "reject_rate"}.issubset(review_keys),
        "AI 质量指标可计算": {"quality_report_count", "avg_quality_score", "auto_ignore_count"}.issubset(ai_keys),
        "失败原因排行结构可用": all(reason.reason and reason.count > 0 for reason in overview.failure_reasons),
        "数据源质量排行结构可用": source_rows_valid,
        "生成时间可读": bool(overview.generated_at),
    }
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"Insight 质量运营验收未通过: {'; '.join(failed)}")
    print(overview.model_dump(mode="json"))


if __name__ == "__main__":
    asyncio.run(main())
