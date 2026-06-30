import asyncio
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from sqlmodel import select

from app.db.session import async_session
from app.models.agent.insight import InsightDataSource, InsightMonitorConfig
from app.services.agent.insight.monitor_execution_service import insight_monitor_execution_service


async def main():
    async with async_session() as db:
        temp = InsightMonitorConfig(
            config_code=f"smoke_{uuid4().hex[:12]}",
            config_name="调度迁移烟测配置",
            monitor_type="custom",
            object_type="custom",
            object_name="调度烟测",
            enabled_modules=["综合舆情"],
            keywords=["调度烟测"],
            fetch_frequency="daily",
            schedule_enabled=True,
            next_run_time=datetime(2000, 1, 1),
            last_schedule_status="waiting",
            visibility_scope="public",
            generation_mode="test",
            status="active",
        )
        db.add(temp)
        await db.commit()
        await db.refresh(temp)

        original_execute = insight_monitor_execution_service.execute_monitor_config

        async def fake_execute(db, row, *, user_id):
            return {"search_results": [SimpleNamespace(hits=[1, 2], candidates=[1])], "query": row.config_name}

        insight_monitor_execution_service.execute_monitor_config = fake_execute
        try:
            result = await insight_monitor_execution_service.run_due_monitor_configs(db, limit=1, user_id=1)
            active_sources = (
                await db.exec(
                    select(InsightDataSource).where(
                        InsightDataSource.is_deleted == 0,
                        InsightDataSource.status == "enabled",
                        InsightDataSource.schedule_enabled == True,  # noqa: E712
                    )
                )
            ).all()
            assert result.executed_count == 1, result
            assert result.executions[0].monitor_config_id == temp.id, result.executions[0]
            assert result.executions[0].data_source_id is None, result.executions[0]
            assert len(active_sources) == 0, len(active_sources)
            print({
                "executed_count": result.executed_count,
                "monitor_config_id": result.executions[0].monitor_config_id,
                "data_source_id": result.executions[0].data_source_id,
                "active_schedulable_data_sources": len(active_sources),
                "message": result.executions[0].message,
            })
        finally:
            insight_monitor_execution_service.execute_monitor_config = original_execute
            temp.is_deleted = 1
            temp.status = "disabled"
            temp.schedule_enabled = False
            temp.next_run_time = None
            await db.commit()

asyncio.run(main())
