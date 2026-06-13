import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightDataSource, InsightTask, InsightTaskStatus
from app.models.system.sys_user import SysUser
from app.services.agent.insight.data_source_service import insight_data_source_service


MARK = "insight-scheduler-retry-cleanup-acceptance"


async def main() -> None:
    token = uuid4().hex[:10]
    created: dict[str, list[int]] = {"users": [], "data_sources": [], "tasks": []}

    async with async_session() as db:
        try:
            user = SysUser(
                username=f"insight_scheduler_retry_{token}",
                full_name=f"Insight 单源重试与清理验收{token}",
                hashed_password="acceptance-only",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(user)
            await db.flush()
            created["users"].append(user.id or 0)

            data_source = InsightDataSource(
                source_code=f"scheduler_retry_{token}",
                source_name=f"单源重试验收源{token}",
                source_type="bocha_news",
                fetch_frequency="hourly",
                fetch_config={"keywords": [f"单源重试验收{token}"], "max_results": 1, "crawl_top_n": 0},
                owner_user_id=user.id,
                visibility_scope="private",
                status="enabled",
                schedule_enabled=False,
                next_run_time=datetime.now() + timedelta(days=1),
                last_schedule_status="paused",
                last_schedule_message="验收预置暂停状态",
                consecutive_failure_count=3,
                last_failure_time=datetime.now() - timedelta(minutes=10),
                auto_paused_reason="验收预置自动暂停原因",
                create_by=MARK,
                update_by=MARK,
            )
            db.add(data_source)
            await db.flush()
            created["data_sources"].append(data_source.id or 0)

            stale_task = InsightTask(
                task_uid=f"insight_stale_{uuid4().hex}",
                task_type="scheduler_tick",
                data_source_id=data_source.id,
                status=InsightTaskStatus.RUNNING,
                progress=30,
                started_at=datetime.now() - timedelta(minutes=60),
                create_time=datetime.now() - timedelta(minutes=60),
                update_time=datetime.now() - timedelta(minutes=60),
                input_payload={"acceptance": MARK, "kind": "stale"},
                create_by=MARK,
                update_by=MARK,
            )
            fresh_task = InsightTask(
                task_uid=f"insight_fresh_{uuid4().hex}",
                task_type="scheduler_tick",
                data_source_id=data_source.id,
                status=InsightTaskStatus.PENDING,
                progress=0,
                started_at=datetime.now(),
                create_time=datetime.now(),
                update_time=datetime.now(),
                input_payload={"acceptance": MARK, "kind": "fresh"},
                create_by=MARK,
                update_by=MARK,
            )
            db.add(stale_task)
            db.add(fresh_task)
            await db.commit()
            await db.refresh(data_source)
            await db.refresh(stale_task)
            await db.refresh(fresh_task)
            created["tasks"].extend([stale_task.id or 0, fresh_task.id or 0])

            retried = await insight_data_source_service.retry_data_source(
                db,
                data_source_id=data_source.id or 0,
                user_id=user.id,
                is_admin=False,
            )
            await db.refresh(data_source)

            cleanup_result = await insight_data_source_service.cleanup_stale_tasks(
                db,
                timeout_minutes=30,
                user_id=user.id,
            )
            await db.refresh(stale_task)
            await db.refresh(fresh_task)

            checks = {
                "单源重试后启用周期采集": retried.schedule_enabled is True and data_source.schedule_enabled is True,
                "单源重试后进入等待调度": retried.last_schedule_status == "waiting" and data_source.last_schedule_status == "waiting",
                "单源重试后下次运行时间已到期": bool(data_source.next_run_time and data_source.next_run_time <= datetime.now()),
                "单源重试后清空暂停原因": retried.auto_paused_reason is None and data_source.auto_paused_reason is None,
                "超时清理只处理一条任务": cleanup_result.cleaned_count == 1,
                "超时清理命中旧任务": stale_task.id in cleanup_result.task_ids,
                "超时任务被标记失败": stale_task.status == InsightTaskStatus.FAILED and stale_task.progress == 100,
                "超时任务写入清理信息": bool((stale_task.output_payload or {}).get("cleanup")),
                "未超时任务不被清理": fresh_task.status == InsightTaskStatus.PENDING and fresh_task.id not in cleanup_result.task_ids,
            }
            for name, passed in checks.items():
                print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            if not all(checks.values()):
                failed = [name for name, passed in checks.items() if not passed]
                raise SystemExit(f"Insight 单源重试与遗留任务清理验收未通过: {'; '.join(failed)}")
            print(
                {
                    "data_source": {
                        "id": data_source.id,
                        "schedule_enabled": data_source.schedule_enabled,
                        "last_schedule_status": data_source.last_schedule_status,
                        "next_run_time": data_source.next_run_time.isoformat() if data_source.next_run_time else None,
                    },
                    "cleanup_result": cleanup_result.model_dump(mode="json"),
                    "stale_task": {
                        "id": stale_task.id,
                        "status": stale_task.status.value,
                        "cleanup": (stale_task.output_payload or {}).get("cleanup"),
                    },
                    "fresh_task": {
                        "id": fresh_task.id,
                        "status": fresh_task.status.value,
                    },
                }
            )
        finally:
            await cleanup(db, created)


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
