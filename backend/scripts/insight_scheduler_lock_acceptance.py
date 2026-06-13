import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.db.session import async_session
from app.schemas.agent.insight.data_source import InsightDataSourceExecuteResponse
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.scheduler_service import insight_scheduler_service


MARK = "insight-scheduler-lock-acceptance"


async def main() -> None:
    original_execute = insight_data_source_service.execute_data_source
    execute_called = False

    async def blocked_execute_data_source(*args, **kwargs) -> InsightDataSourceExecuteResponse:
        nonlocal execute_called
        execute_called = True
        raise AssertionError("advisory lock held; data source execution should not be called")

    async with async_session() as lock_db:
        locked = bool(
            (
                await lock_db.exec(
                    text("SELECT pg_try_advisory_lock(:lock_id)").bindparams(
                        lock_id=settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID
                    ),
                )
            ).scalar_one()
        )
        if not locked:
            raise SystemExit("Insight 调度互斥验收未通过: 无法预先持有 advisory lock")

        try:
            insight_data_source_service.execute_data_source = blocked_execute_data_source
            result = await insight_scheduler_service.run_once(triggered_by=MARK)
            last_result = insight_scheduler_service.status().get("last_result") or {}
            checks = {
                "互斥锁占用时不执行扫描": result.checked_count == 0 and result.due_count == 0,
                "互斥锁占用时不执行数据源": not execute_called,
                "互斥锁占用时返回 skipped": last_result.get("skipped") is True,
                "互斥锁占用时记录触发来源": last_result.get("triggered_by") == MARK,
                "互斥锁占用时不创建调度任务": "task_id" not in last_result,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 调度互斥验收未通过: {'; '.join(failed)}")
            print({"last_result": last_result, "lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID})
        finally:
            insight_data_source_service.execute_data_source = original_execute
            await lock_db.exec(
                text("SELECT pg_advisory_unlock(:lock_id)").bindparams(
                    lock_id=settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID
                ),
            )
            await lock_db.commit()


if __name__ == "__main__":
    asyncio.run(main())
