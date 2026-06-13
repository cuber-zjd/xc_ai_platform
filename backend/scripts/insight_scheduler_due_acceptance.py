import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlmodel import select

from app.core.config import settings
from app.db.session import async_session
from app.models.agent.insight import InsightDataSource, InsightTask
from app.models.system.sys_user import SysUser
from app.schemas.agent.insight.data_source import InsightDataSourceExecuteResponse
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.scheduler_service import insight_scheduler_service


MARK = "insight-scheduler-due-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "data_sources": [], "tasks": []}
    original_execute = insight_data_source_service.execute_data_source
    original_batch_limit = settings.INSIGHT_SCHEDULER_BATCH_LIMIT

    async with async_session() as db:
        try:
            user = SysUser(
                username=f"insight_scheduler_due_{token}",
                full_name=f"Insight调度验收{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(user)
            await db.flush()
            created["users"].append(user.id or 0)

            due_source = InsightDataSource(
                source_code=f"scheduler_due_{token}",
                source_name=f"调度到期验收源{token}",
                source_type="bocha_news",
                fetch_frequency="hourly",
                fetch_config={"keywords": [f"调度验收{token}"], "max_results": 1, "crawl_top_n": 0},
                owner_user_id=user.id,
                visibility_scope="private",
                status="enabled",
                schedule_enabled=True,
                next_run_time=datetime(2000, 1, 1),
                last_schedule_status="waiting",
                create_by=MARK,
                update_by=MARK,
            )
            future_source = InsightDataSource(
                source_code=f"scheduler_future_{token}",
                source_name=f"调度未到期验收源{token}",
                source_type="bocha_news",
                fetch_frequency="hourly",
                fetch_config={"keywords": [f"调度未到期{token}"], "max_results": 1, "crawl_top_n": 0},
                owner_user_id=user.id,
                visibility_scope="private",
                status="enabled",
                schedule_enabled=True,
                next_run_time=datetime.now() + timedelta(days=1),
                last_schedule_status="waiting",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(due_source)
            db.add(future_source)
            await db.commit()
            await db.refresh(due_source)
            await db.refresh(future_source)
            created["data_sources"].extend([due_source.id or 0, future_source.id or 0])

            async def fake_execute_data_source(db_arg, data_source_id, payload, user_id, *, is_admin=False):
                _ = payload, user_id, is_admin
                row = await insight_data_source_service._get_data_source(db_arg, data_source_id, is_admin=True)
                row.last_fetch_time = datetime.now()
                row.last_success_time = datetime.now()
                await db_arg.commit()
                await db_arg.refresh(row)
                return InsightDataSourceExecuteResponse(
                    data_source=await insight_data_source_service._to_read_with_company(db_arg, row),
                    auto_review_summary={"mode": "acceptance_mock"},
                )

            insight_data_source_service.execute_data_source = fake_execute_data_source
            settings.INSIGHT_SCHEDULER_BATCH_LIMIT = 1

            result = await insight_scheduler_service.run_once(triggered_by=MARK)
            await db.refresh(due_source)
            await db.refresh(future_source)
            await collect_scheduler_tasks(db, created, token=None)

            checks = {
                "只执行一条到期数据源": len(result.executions) == 1,
                "执行目标为验收数据源": bool(result.executions and result.executions[0].data_source_id == due_source.id),
                "到期数据源执行成功": due_source.last_schedule_status == "success",
                "到期数据源写入下次运行时间": bool(due_source.next_run_time and due_source.next_run_time > datetime.now()),
                "到期数据源失败计数清零": due_source.consecutive_failure_count == 0,
                "未到期数据源未执行": future_source.last_schedule_status == "waiting",
                "调度器记录最近结果": bool(insight_scheduler_service.status().get("last_result")),
                "调度器最近结果关联任务": bool((insight_scheduler_service.status().get("last_result") or {}).get("task_id")),
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 到期调度验收未通过: {'; '.join(failed)}")
            print(
                {
                    "checked_count": result.checked_count,
                    "due_count": result.due_count,
                    "executed_count": result.executed_count,
                    "failed_count": result.failed_count,
                    "executions": [item.model_dump(mode="json") for item in result.executions],
                }
            )
        finally:
            insight_data_source_service.execute_data_source = original_execute
            settings.INSIGHT_SCHEDULER_BATCH_LIMIT = original_batch_limit
            await cleanup(db, created)


async def collect_scheduler_tasks(db, created: dict[str, list[int]], token: str | None) -> None:
    _ = token
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
