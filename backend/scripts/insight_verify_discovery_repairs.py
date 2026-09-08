"""验证搜索到入库的真实链路，不调用报告或通知任务。"""

import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlmodel import select

from app.core.config import settings
from app.db.session import async_session
from app.models.agent.insight import InsightMonitorConfig
from app.services.agent.insight.monitor_execution_service import insight_monitor_execution_service


async def main():
    async with async_session() as db:
        locked = (await db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID})).scalar_one()
        if not locked:
            raise RuntimeError("已有采集任务运行，本次验证退出")
        try:
            rows = list((await db.exec(select(InsightMonitorConfig).where(
                InsightMonitorConfig.is_deleted == 0, InsightMonitorConfig.status == "active",
            ).order_by(InsightMonitorConfig.id).limit(2))).all())
            result = await insight_monitor_execution_service._execute_grouped_daily_discovery(
                db, [row.id for row in rows], user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                freshness_override="7d", published_start=(datetime.now() - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0),
                published_end=datetime.now(),
            )
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        finally:
            await db.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID})
            await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
