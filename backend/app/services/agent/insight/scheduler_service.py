import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.core.config import settings
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.insight import InsightTask, InsightTaskStatus
from app.schemas.agent.insight.data_source import InsightDataSourceScheduleRunResponse
from app.services.agent.insight.data_source_service import insight_data_source_service
from app.services.agent.insight.report_subscription_service import insight_report_subscription_service


class InsightSchedulerService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._enabled = settings.INSIGHT_SCHEDULER_ENABLED
        self._last_tick_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._next_tick_at: datetime | None = None
        self._last_error: str | None = None
        self._last_result: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        config_health = self._config_health()
        return {
            "enabled": self._enabled,
            "running": self.running,
            "interval_seconds": settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS,
            "batch_limit": settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
            "startup_delay_seconds": settings.INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS,
            "advisory_lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID,
            "scheduler_user_id": settings.INSIGHT_SCHEDULER_USER_ID,
            "failure_pause_threshold": settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD,
            "config_health": config_health["level"],
            "config_warnings": config_health["warnings"],
            "config_recommendations": config_health["recommendations"],
            "last_tick_at": self._last_tick_at,
            "last_success_at": self._last_success_at,
            "next_tick_at": self._next_tick_at if self.running else None,
            "last_error": self._last_error,
            "last_result": self._last_result,
        }

    def _config_health(self) -> dict[str, Any]:
        warnings: list[str] = []
        recommendations: list[str] = []
        if not self._enabled:
            warnings.append("INSIGHT_SCHEDULER_ENABLED 当前未开启，生产环境不会自动执行周期采集。")
            recommendations.append("生产环境建议设置 INSIGHT_SCHEDULER_ENABLED=true，并通过状态接口确认 running=true。")
        if settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS <= 0:
            warnings.append("INSIGHT_SCHEDULER_INTERVAL_SECONDS 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS < 60:
            recommendations.append("扫描间隔低于 60 秒，生产环境需确认外部搜索和抓取服务限流容量。")
        if settings.INSIGHT_SCHEDULER_BATCH_LIMIT <= 0:
            warnings.append("INSIGHT_SCHEDULER_BATCH_LIMIT 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_BATCH_LIMIT > 50:
            recommendations.append("单批上限大于 50，生产环境需确认数据库、搜索 API 和 Firecrawl 的并发承载能力。")
        if settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD <= 0:
            warnings.append("INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD 必须大于 0，否则无法可靠自动暂停失败数据源。")
        if settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID <= 0:
            warnings.append("INSIGHT_SCHEDULER_ADVISORY_LOCK_ID 必须为正整数，用于多实例互斥。")
        if settings.INSIGHT_SCHEDULER_USER_ID <= 0:
            warnings.append("INSIGHT_SCHEDULER_USER_ID 必须为有效用户 ID，用于记录系统调度执行人。")
        level = "ready" if not warnings else "warning"
        return {
            "level": level,
            "warnings": warnings,
            "recommendations": recommendations,
        }

    async def start(self) -> None:
        self._enabled = True
        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._next_tick_at = datetime.now() + timedelta(seconds=settings.INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS)
        self._task = asyncio.create_task(self._loop(), name="insight-scheduler")
        logger.info("Insight 调度器已启动")

    async def stop(self) -> None:
        self._enabled = False
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
            self._next_tick_at = None
        logger.info("Insight 调度器已停止")

    async def start_from_settings(self) -> None:
        if settings.INSIGHT_SCHEDULER_ENABLED:
            await self.start()
        else:
            logger.info("Insight 调度器未启用，设置 INSIGHT_SCHEDULER_ENABLED=true 后自动启动")

    async def run_once(self, *, triggered_by: str = "manual") -> InsightDataSourceScheduleRunResponse:
        self._last_tick_at = datetime.now()
        async with async_session() as db:
            locked = await self._try_advisory_lock(db)
            if not locked:
                result = InsightDataSourceScheduleRunResponse(
                    checked_count=0,
                    due_count=0,
                    executed_count=0,
                    failed_count=0,
                    executions=[],
                )
                self._last_result = {
                    "skipped": True,
                    "reason": "另一个调度器实例正在执行",
                    "triggered_by": triggered_by,
                }
                return result

            task = InsightTask(
                task_uid=f"insight_scheduler_{uuid4().hex}",
                task_type="scheduler_tick",
                status=InsightTaskStatus.RUNNING,
                progress=10,
                started_at=datetime.now(),
                input_payload={
                    "triggered_by": triggered_by,
                    "batch_limit": settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                    "lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID,
                },
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            try:
                result = await insight_data_source_service.run_due_data_sources(
                    db,
                    limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                    user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                )
                report_result = await insight_report_subscription_service.run_due_subscriptions(
                    db,
                    limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                    triggered_by=triggered_by,
                )
                total_failed_count = result.failed_count + report_result.failed_count
                task.status = InsightTaskStatus.SUCCESS if total_failed_count == 0 else InsightTaskStatus.FAILED
                task.progress = 100
                task.finished_at = datetime.now()
                task.output_payload = {
                    "data_sources": result.model_dump(mode="json"),
                    "report_subscriptions": report_result.model_dump(mode="json"),
                }
                task.error_message = None if total_failed_count == 0 else f"{result.failed_count} 个数据源执行失败，{report_result.failed_count} 个定时报告执行失败"
                self._last_success_at = datetime.now() if total_failed_count == 0 else self._last_success_at
                self._last_error = task.error_message
                self._last_result = {
                    "data_sources": result.model_dump(mode="json"),
                    "report_subscriptions": report_result.model_dump(mode="json"),
                    "triggered_by": triggered_by,
                    "task_id": task.id,
                }
                await db.commit()
                return result
            except Exception as exc:
                task.status = InsightTaskStatus.FAILED
                task.progress = 100
                task.finished_at = datetime.now()
                task.error_message = str(exc)
                task.output_payload = {"triggered_by": triggered_by, "error": str(exc)}
                self._last_error = str(exc)
                self._last_result = {"triggered_by": triggered_by, "error": str(exc), "task_id": task.id}
                await db.commit()
                raise
            finally:
                await self._release_advisory_lock(db)

    async def _loop(self) -> None:
        await self._sleep_or_stop(settings.INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS)
        while self._enabled and not self._stop_event.is_set():
            try:
                await self.run_once(triggered_by="scheduler")
            except Exception as exc:
                logger.exception("Insight 调度器执行失败：%s", exc)
            self._next_tick_at = datetime.now() + timedelta(seconds=settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS)
            await self._sleep_or_stop(settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS)

    async def _sleep_or_stop(self, seconds: int) -> None:
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _try_advisory_lock(self, db) -> bool:
        result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )
        return bool(result.scalar_one())

    async def _release_advisory_lock(self, db) -> None:
        await db.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )


insight_scheduler_service = InsightSchedulerService()
