import asyncio
from datetime import datetime
from uuid import uuid4

from sqlmodel import select

from app.core.config import settings
from app.db.session import async_session
from app.models.agent.insight import InsightDataSource, InsightTask
from app.models.system.sys_user import SysUser
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.scheduler_service import insight_scheduler_service


MARK = "insight-scheduler-failure-pause-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "data_sources": [], "tasks": []}
    original_execute = insight_data_source_service.execute_data_source
    original_batch_limit = settings.INSIGHT_SCHEDULER_BATCH_LIMIT
    threshold = max(settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD, 1)
    error_message = f"C4 acceptance forced failure {token}"

    async with async_session() as db:
        try:
            user = SysUser(
                username=f"insight_scheduler_failure_{token}",
                full_name=f"Insight 调度失败暂停验收{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(user)
            await db.flush()
            created["users"].append(user.id or 0)

            data_source = InsightDataSource(
                source_code=f"scheduler_failure_{token}",
                source_name=f"调度连续失败暂停验收源{token}",
                source_type="bocha_news",
                fetch_frequency="hourly",
                fetch_config={"keywords": [f"调度失败暂停验收{token}"], "max_results": 1, "crawl_top_n": 0},
                owner_user_id=user.id,
                visibility_scope="private",
                status="enabled",
                schedule_enabled=True,
                next_run_time=datetime(1900, 1, 1),
                last_schedule_status="waiting",
                consecutive_failure_count=threshold - 1,
                create_by=MARK,
                update_by=MARK,
            )
            db.add(data_source)
            await db.commit()
            await db.refresh(data_source)
            created["data_sources"].append(data_source.id or 0)

            async def failed_execute_data_source(*args, **kwargs):
                raise RuntimeError(error_message)

            insight_data_source_service.execute_data_source = failed_execute_data_source
            settings.INSIGHT_SCHEDULER_BATCH_LIMIT = 1

            result = await insight_scheduler_service.run_once(triggered_by=MARK)
            await db.refresh(data_source)
            await collect_scheduler_tasks(created)

            last_result = insight_scheduler_service.status().get("last_result") or {}
            execution = result.executions[0] if result.executions else None
            checks = {
                "只执行一条验收数据源": len(result.executions) == 1 and bool(execution),
                "执行目标为失败暂停验收源": bool(execution and execution.data_source_id == data_source.id),
                "调度结果记录失败": result.failed_count == 1 and result.executed_count == 0,
                "达到阈值后关闭周期采集": data_source.schedule_enabled is False,
                "达到阈值后状态为 paused": data_source.last_schedule_status == "paused",
                "失败次数达到暂停阈值": data_source.consecutive_failure_count >= threshold,
                "写入最近失败时间": data_source.last_failure_time is not None,
                "写入自动暂停原因": bool(data_source.auto_paused_reason and error_message in data_source.auto_paused_reason),
                "暂停后清空或保留下次时间均不阻碍禁用": data_source.next_run_time is not None,
                "调度器最近结果关联任务": bool(last_result.get("task_id")),
                "调度器最近结果记录触发来源": last_result.get("triggered_by") == MARK,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 连续失败自动暂停验收未通过: {'; '.join(failed)}")
            print(
                {
                    "threshold": threshold,
                    "checked_count": result.checked_count,
                    "due_count": result.due_count,
                    "executed_count": result.executed_count,
                    "failed_count": result.failed_count,
                    "data_source": {
                        "id": data_source.id,
                        "schedule_enabled": data_source.schedule_enabled,
                        "last_schedule_status": data_source.last_schedule_status,
                        "consecutive_failure_count": data_source.consecutive_failure_count,
                        "auto_paused_reason": data_source.auto_paused_reason,
                    },
                    "last_result": last_result,
                }
            )
        finally:
            insight_data_source_service.execute_data_source = original_execute
            settings.INSIGHT_SCHEDULER_BATCH_LIMIT = original_batch_limit
            await cleanup(db, created)


async def collect_scheduler_tasks(created: dict[str, list[int]]) -> None:
    last_result = insight_scheduler_service.status().get("last_result") or {}
    task_id = last_result.get("task_id")
    if isinstance(task_id, int):
        created["tasks"].append(task_id)


async def cleanup(db, created: dict[str, list[int]]) -> None:
    model_map = {
        "tasks": InsightTask,
        "data_sources": InsightDataSource,
        "users": SysUser,
    }
    for key, model in model_map.items():
        ids = [item_id for item_id in created[key] if item_id]
        if not ids:
            continue
        rows = list((await db.exec(select(model).where(model.id.in_(ids)))).all())
        for row in rows:
            row.is_deleted = 1
            row.update_by = f"{MARK}-cleanup"
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
