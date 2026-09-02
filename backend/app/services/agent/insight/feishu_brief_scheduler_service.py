import asyncio
from datetime import datetime

from sqlalchemy import text
from sqlmodel import func, select

from app.core.config import settings
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.insight import (
    InsightFeishuBriefOccurrence,
    InsightFeishuBriefPlan,
    InsightFeishuBriefRun,
)
from app.services.agent.insight.feishu_brief_service import insight_feishu_brief_service


class InsightFeishuBriefSchedulerService:
    """按简报计划实际时间运行，不依赖每日采集任务的单次扫描。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start_from_settings(self) -> None:
        if not settings.INSIGHT_FEISHU_BRIEF_ENABLED or self.running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._loop(), name="insight-feishu-brief-scheduler")
        logger.info("飞书简报定时器已启动")

    async def stop(self) -> None:
        if not self._task:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=10)
        except asyncio.TimeoutError:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        finally:
            self._task = None
        logger.info("飞书简报定时器已停止")

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                next_event = await self._next_event_time()
                wait_seconds = 60.0
                if next_event:
                    wait_seconds = min(max((next_event - datetime.now()).total_seconds(), 0.0), 60.0)
                if wait_seconds > 0:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
                        continue
                    except asyncio.TimeoutError:
                        pass
                await self._run_due()
            except Exception as exc:
                logger.exception("飞书简报定时器执行失败：{}", exc)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass

    async def _next_event_time(self) -> datetime | None:
        async with async_session() as db:
            next_plan = (
                await db.exec(
                    select(func.min(InsightFeishuBriefPlan.next_run_time)).where(
                        InsightFeishuBriefPlan.is_deleted == 0,
                        InsightFeishuBriefPlan.status == "active",
                    )
                )
            ).one()
            next_delivery = (
                await db.exec(
                    select(func.min(InsightFeishuBriefRun.afternoon_push_scheduled_at)).where(
                        InsightFeishuBriefRun.is_deleted == 0,
                        InsightFeishuBriefRun.afternoon_push_status == "pending",
                    )
                )
            ).one()
            next_review = (
                await db.exec(
                    select(func.min(InsightFeishuBriefRun.review_push_scheduled_at)).where(
                        InsightFeishuBriefRun.is_deleted == 0,
                        InsightFeishuBriefRun.review_push_status == "pending",
                    )
                )
            ).one()
            next_occurrence = (
                await db.exec(
                    select(func.min(InsightFeishuBriefOccurrence.generation_scheduled_at)).where(
                        InsightFeishuBriefOccurrence.is_deleted == 0,
                        InsightFeishuBriefOccurrence.status == "pending",
                    )
                )
            ).one()
        values = [
            item for item in (next_plan, next_occurrence, next_review, next_delivery) if item is not None
        ]
        return min(values) if values else None

    async def _run_due(self) -> None:
        async with async_session() as db:
            lock_id = settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID + 17
            locked = bool(
                (
                    await db.execute(
                        text("SELECT pg_try_advisory_lock(:lock_id)"),
                        {"lock_id": lock_id},
                    )
                ).scalar_one()
            )
            if not locked:
                return
            try:
                plan_result = await insight_feishu_brief_service.run_due_plans(
                    db,
                    limit=20,
                    trigger_type="brief_scheduler",
                )
                review_result = await insight_feishu_brief_service.run_due_review_pushes(
                    db,
                    limit=50,
                )
                delivery_result = await insight_feishu_brief_service.run_due_afternoon_pushes(
                    db,
                    limit=50,
                )
                if plan_result.due_count or review_result["due_count"] or delivery_result["due_count"]:
                    logger.info(
                        "飞书简报定时执行完成：生成 {} 个，审阅推送 {} 个，正式推送 {} 个",
                        plan_result.due_count,
                        review_result["due_count"],
                        delivery_result["due_count"],
                    )
            finally:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
                await db.commit()


insight_feishu_brief_scheduler_service = InsightFeishuBriefSchedulerService()
