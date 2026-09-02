import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.llm_usage import collect_llm_usage
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.insight import InsightTask, InsightTaskStatus
from app.schemas.agent.insight.data_source import InsightDataSourceScheduleRunResponse
from app.schemas.agent.insight.feishu import InsightFeishuSyncRequest
from app.schemas.agent.insight.task import InsightSchedulerRunLogRead
from app.schemas.page import Page
from app.services.agent.insight.feishu_bitable_service import insight_feishu_bitable_service
from app.services.agent.insight.monitor_execution_service import insight_monitor_execution_service
from app.services.agent.insight.report_subscription_service import insight_report_subscription_service


class InsightSchedulerService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._baidu_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._enabled = settings.INSIGHT_SCHEDULER_ENABLED
        self._last_tick_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._next_tick_at: datetime | None = None
        self._last_error: str | None = None
        self._last_result: dict[str, Any] | None = None
        self._next_baidu_tick_at: datetime | None = None
        self._last_baidu_result: dict[str, Any] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        config_health = self._config_health()
        return {
            "enabled": self._enabled,
            "auto_start": settings.INSIGHT_SCHEDULER_AUTO_START,
            "running": self.running,
            "trigger_mode": settings.INSIGHT_SCHEDULER_TRIGGER_MODE,
            "daily_time": settings.INSIGHT_SCHEDULER_DAILY_TIME,
            "timezone": settings.INSIGHT_SCHEDULER_TIMEZONE,
            "interval_seconds": settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS,
            "batch_limit": settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
            "daily_discovery_enabled": settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_ENABLED,
            "daily_discovery_freshness": settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_FRESHNESS,
            "baidu_spread_enabled": settings.INSIGHT_SCHEDULER_BAIDU_SPREAD_ENABLED,
            "baidu_slot_interval_seconds": settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS,
            "next_baidu_tick_at": self._next_baidu_tick_at,
            "last_baidu_result": self._last_baidu_result,
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
            recommendations.append("如需执行周期采集，可通过调度器启动接口手动启动，或同时设置 INSIGHT_SCHEDULER_ENABLED=true 与 INSIGHT_SCHEDULER_AUTO_START=true。")
        elif not settings.INSIGHT_SCHEDULER_AUTO_START:
            recommendations.append("INSIGHT_SCHEDULER_AUTO_START=false，后端重启后不会进入定时等待；需要人工启动调度器或由外部任务调用单次扫描接口。")
        trigger_mode = settings.INSIGHT_SCHEDULER_TRIGGER_MODE.strip().lower()
        if trigger_mode not in {"daily", "fixed_interval"}:
            warnings.append("INSIGHT_SCHEDULER_TRIGGER_MODE 仅支持 daily 或 fixed_interval。")
        if trigger_mode == "daily":
            try:
                self._parse_daily_time()
            except ValueError as exc:
                warnings.append(str(exc))
            try:
                ZoneInfo(settings.INSIGHT_SCHEDULER_TIMEZONE)
            except ZoneInfoNotFoundError:
                warnings.append(f"INSIGHT_SCHEDULER_TIMEZONE 无法识别：{settings.INSIGHT_SCHEDULER_TIMEZONE}")
        if settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS <= 0:
            warnings.append("INSIGHT_SCHEDULER_INTERVAL_SECONDS 必须大于 0。")
        elif trigger_mode == "fixed_interval" and settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS < 60:
            recommendations.append("扫描间隔低于 60 秒，生产环境需确认外部搜索和抓取服务限流容量。")
        if settings.INSIGHT_SCHEDULER_BATCH_LIMIT <= 0:
            warnings.append("INSIGHT_SCHEDULER_BATCH_LIMIT 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_BATCH_LIMIT > 50:
            recommendations.append("单批上限大于 50，生产环境需确认数据库、搜索 API 和 Firecrawl 的并发承载能力。")
        if settings.INSIGHT_SCHEDULER_BAIDU_CONCURRENCY <= 0:
            warnings.append("INSIGHT_SCHEDULER_BAIDU_CONCURRENCY 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_BAIDU_CONCURRENCY > 5:
            recommendations.append("百度资讯并发高于 5，可能增加触发反爬的风险。")
        if settings.INSIGHT_SCHEDULER_BAIDU_SPREAD_ENABLED:
            if settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS < 300:
                warnings.append("百度全天分片间隔不得低于 300 秒，避免再次触发反爬。")
            elif settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS > 3600:
                recommendations.append("百度全天分片间隔超过 1 小时，单个时间槽可能堆积较多监测对象。")
        if settings.INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE < 2:
            warnings.append("INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE 不能小于 2。")
        if settings.INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE <= 0:
            warnings.append("INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE > 4:
            recommendations.append("豆包联网搜索单组对象数大于 4，长查询可能增加超时和漏检风险。")
        if settings.INSIGHT_SCHEDULER_GROUPED_AI_TIMEOUT_SECONDS < 120:
            recommendations.append("豆包联网搜索总时限低于 120 秒，联网检索和流式整理可能无法完整返回。")
        if (
            settings.INSIGHT_DOUBAO_SEARCH_READ_TIMEOUT_SECONDS
            < settings.INSIGHT_SCHEDULER_GROUPED_AI_TIMEOUT_SECONDS
        ):
            recommendations.append("豆包流式读取时限低于调度总时限，请求可能在调度器接管前提前中断。")
        daily_adapter_codes = [
            item.strip()
            for item in settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CHANNEL_CODES.split(",")
            if item.strip()
        ]
        if not daily_adapter_codes:
            warnings.append("重点渠道每日采集列表为空，头条、搜狐等垂直渠道不会得到每日执行保证。")
        if settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY <= 0:
            warnings.append("INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY 必须大于 0。")
        elif settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY > 3:
            recommendations.append("重点站点并发高于 3，可能增加反爬、封禁和浏览器资源占用风险。")
        if settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_TOPIC_LIMIT <= 0:
            warnings.append("INSIGHT_SCHEDULER_DAILY_ADAPTER_TOPIC_LIMIT 必须大于 0。")
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
        self._stop_event = asyncio.Event()
        if not self.running:
            self._next_tick_at = self._next_scheduled_tick()
            self._task = asyncio.create_task(self._loop(), name="insight-scheduler")
            logger.info("Insight 调度器已启动，下一次执行时间：{}", self._next_tick_at)
        if settings.INSIGHT_SCHEDULER_BAIDU_SPREAD_ENABLED and (
            self._baidu_task is None or self._baidu_task.done()
        ):
            self._next_baidu_tick_at = self._next_baidu_slot_tick()
            self._baidu_task = asyncio.create_task(
                self._baidu_loop(),
                name="insight-baidu-spread-scheduler",
            )
            logger.info("百度全天分片调度器已启动，下一时间槽：{}", self._next_baidu_tick_at)

    async def stop(self) -> None:
        self._enabled = False
        tasks = [task for task in (self._task, self._baidu_task) if task is not None]
        if not tasks:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
        except asyncio.TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._task = None
            self._baidu_task = None
            self._next_tick_at = None
            self._next_baidu_tick_at = None
        logger.info("Insight 调度器已停止")

    async def start_from_settings(self) -> None:
        if settings.INSIGHT_SCHEDULER_ENABLED and settings.INSIGHT_SCHEDULER_AUTO_START:
            await self.start()
        elif settings.INSIGHT_SCHEDULER_ENABLED:
            logger.info("Insight 调度器允许启用，但未配置自动启动；后端重启不会自动采集")
        else:
            logger.info("Insight 调度器未启用；如需后台采集，请先设置 INSIGHT_SCHEDULER_ENABLED=true，再通过接口或外部定时任务启动")

    async def run_once(self, *, triggered_by: str = "manual") -> InsightDataSourceScheduleRunResponse:
        self._last_tick_at = self._now()
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
                started_at=self._now(),
                input_payload={
                    "triggered_by": triggered_by,
                    "trigger_mode": settings.INSIGHT_SCHEDULER_TRIGGER_MODE,
                    "daily_time": settings.INSIGHT_SCHEDULER_DAILY_TIME,
                    "timezone": settings.INSIGHT_SCHEDULER_TIMEZONE,
                    "batch_limit": settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                    "daily_discovery_enabled": settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_ENABLED,
                    "daily_discovery_freshness": settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_FRESHNESS,
                    "daily_adapter_channel_codes": [
                        item.strip()
                        for item in settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CHANNEL_CODES.split(",")
                        if item.strip()
                    ],
                    "lock_id": settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID,
                },
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            with collect_llm_usage() as usage_collector:
                try:
                    daily_discovery: dict[str, Any] = {
                        "enabled": settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_ENABLED,
                        "checked_count": 0,
                        "signal_monitor_config_ids": [],
                    }
                    if settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_ENABLED:
                        daily_discovery = {
                            "enabled": True,
                            **await insight_monitor_execution_service.run_daily_discovery_all(
                                db,
                                user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                                include_baidu=not settings.INSIGHT_SCHEDULER_BAIDU_SPREAD_ENABLED,
                            ),
                        }
                    result = await insight_monitor_execution_service.run_due_monitor_configs(
                        db,
                        limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                        user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                        priority_row_ids=list(daily_discovery.get("signal_monitor_config_ids") or []),
                    )
                    report_result = await insight_report_subscription_service.run_due_subscriptions(
                        db,
                        limit=settings.INSIGHT_SCHEDULER_BATCH_LIMIT,
                        triggered_by=triggered_by,
                    )
                    feishu_result: dict[str, Any] | None = None
                    feishu_error: str | None = None
                    if settings.INSIGHT_FEISHU_SYNC_ENABLED and insight_feishu_bitable_service.get_options().configured:
                        sync_end = self._now().replace(hour=23, minute=59, second=59, microsecond=999999)
                        sync_start = (sync_end - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        try:
                            sync_response = await insight_feishu_bitable_service.sync_intelligences(
                                db,
                                InsightFeishuSyncRequest(
                                    scope="date_range",
                                    date_from=sync_start,
                                    date_to=sync_end,
                                    update_existing=True,
                                    ensure_metadata=True,
                                ),
                                user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                                is_admin=True,
                            )
                            feishu_result = sync_response.model_dump(mode="json")
                        except Exception as exc:
                            feishu_error = str(exc)[:1000]
                    total_failed_count = (
                        result.failed_count
                        + report_result.failed_count
                        + (1 if feishu_error else 0)
                    )
                    task.status = InsightTaskStatus.SUCCESS if total_failed_count == 0 else InsightTaskStatus.FAILED
                    task.progress = 100
                    task.finished_at = self._now()
                    task.output_payload = {
                        "daily_discovery": daily_discovery,
                        "monitor_configs": result.model_dump(mode="json"),
                        "report_subscriptions": report_result.model_dump(mode="json"),
                        "feishu_briefs": {"handled_by": "independent_scheduler"},
                        "feishu_sync": feishu_result,
                        "feishu_sync_error": feishu_error,
                        "token_usage": usage_collector.snapshot(),
                    }
                    task.error_message = (
                        None
                        if total_failed_count == 0
                        else (
                            f"{result.failed_count} 个监测配置执行失败，"
                            f"{report_result.failed_count} 个定时报告执行失败，"
                            f"{'，飞书同步失败：' + feishu_error if feishu_error else ''}"
                        )
                    )
                    self._last_success_at = self._now() if total_failed_count == 0 else self._last_success_at
                    self._last_error = task.error_message
                    self._last_result = {
                        "daily_discovery": daily_discovery,
                        "monitor_configs": result.model_dump(mode="json"),
                        "report_subscriptions": report_result.model_dump(mode="json"),
                        "feishu_briefs": {"handled_by": "independent_scheduler"},
                        "feishu_sync": feishu_result,
                        "feishu_sync_error": feishu_error,
                        "token_usage": usage_collector.snapshot(),
                        "triggered_by": triggered_by,
                        "task_id": task.id,
                    }
                    await db.commit()
                    await self._release_advisory_lock(db)
                    return result
                except Exception as exc:
                    task.status = InsightTaskStatus.FAILED
                    task.progress = 100
                    task.finished_at = self._now()
                    task.error_message = str(exc)
                    task.output_payload = {
                        "triggered_by": triggered_by,
                        "error": str(exc),
                        "token_usage": usage_collector.snapshot(),
                    }
                    self._last_error = str(exc)
                    self._last_result = {
                        "triggered_by": triggered_by,
                        "error": str(exc),
                        "token_usage": usage_collector.snapshot(),
                        "task_id": task.id,
                    }
                    await db.commit()
                    await self._release_advisory_lock(db)
                    raise

    async def list_run_logs(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Page[InsightSchedulerRunLogRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [
            InsightTask.is_deleted == 0,
            InsightTask.task_type.in_(("scheduler_tick", "baidu_spread_tick")),
        ]
        if status:
            filters.append(InsightTask.status == status.upper())
        if date_from:
            filters.append(InsightTask.started_at >= date_from)
        if date_to:
            filters.append(InsightTask.started_at <= date_to)
        total = (await db.exec(select(func.count()).select_from(InsightTask).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightTask)
                    .where(*filters)
                    .order_by(InsightTask.started_at.desc().nullslast(), InsightTask.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            ).all()
        )
        return Page(
            total=total,
            items=[self._to_run_log(item) for item in rows],
            page=page,
            size=size,
        )

    def _to_run_log(self, task: InsightTask) -> InsightSchedulerRunLogRead:
        input_payload = task.input_payload or {}
        output_payload = task.output_payload or {}
        monitor_result = output_payload.get("monitor_configs") or {}
        daily_discovery = output_payload.get("daily_discovery") or {}
        report_result = output_payload.get("report_subscriptions") or {}
        feishu_result = output_payload.get("feishu_sync") or {}
        token_usage = output_payload.get("token_usage") or {}
        if task.task_type == "baidu_spread_tick":
            daily_discovery = {
                "checked_count": output_payload.get("scheduled_count"),
                "hit_count": output_payload.get("hit_count"),
                "candidate_count": output_payload.get("candidate_count"),
                "baidu_failed_count": output_payload.get("failed_count"),
            }
        duration_seconds = 0.0
        if task.started_at and task.finished_at:
            duration_seconds = max((task.finished_at - task.started_at).total_seconds(), 0.0)
        return InsightSchedulerRunLogRead(
            id=task.id or 0,
            task_uid=task.task_uid,
            status=task.status.value if hasattr(task.status, "value") else str(task.status),
            triggered_by=str(
                input_payload.get("triggered_by")
                or output_payload.get("triggered_by")
                or ("baidu_spread" if task.task_type == "baidu_spread_tick" else "scheduler")
            ),
            started_at=task.started_at,
            finished_at=task.finished_at,
            duration_seconds=round(duration_seconds, 2),
            discovery_checked_count=int(daily_discovery.get("checked_count") or 0),
            discovery_hit_count=int(daily_discovery.get("hit_count") or 0),
            discovery_candidate_count=int(daily_discovery.get("candidate_count") or 0),
            discovery_failed_count=int(daily_discovery.get("baidu_failed_count") or 0)
            + int(daily_discovery.get("grouped_failed_count") or 0),
            checked_count=int(monitor_result.get("checked_count") or 0),
            due_count=int(monitor_result.get("due_count") or 0),
            executed_count=int(monitor_result.get("executed_count") or 0),
            failed_count=int(monitor_result.get("failed_count") or 0),
            report_executed_count=int(report_result.get("executed_count") or 0),
            report_failed_count=int(report_result.get("failed_count") or 0),
            feishu_created_count=int(feishu_result.get("created_count") or 0),
            feishu_updated_count=int(feishu_result.get("updated_count") or 0),
            feishu_failed_count=int(
                feishu_result.get("failed_count") or (1 if output_payload.get("feishu_sync_error") else 0)
            ),
            input_tokens=int(token_usage.get("input_tokens") or 0),
            output_tokens=int(token_usage.get("output_tokens") or 0),
            total_tokens=int(token_usage.get("total_tokens") or 0),
            model_call_count=int(token_usage.get("call_count") or 0),
            token_models=list(token_usage.get("models") or []),
            error_message=task.error_message,
            details=output_payload,
        )

    async def _loop(self) -> None:
        while self._enabled and not self._stop_event.is_set():
            if self._next_tick_at is None:
                self._next_tick_at = self._next_scheduled_tick()
            await self._sleep_or_stop(self._seconds_until(self._next_tick_at))
            if not self._enabled or self._stop_event.is_set():
                break
            try:
                await self.run_once(triggered_by=f"scheduler:{settings.INSIGHT_SCHEDULER_TRIGGER_MODE}")
            except Exception as exc:
                logger.exception("Insight 调度器执行失败：{}", exc)
            self._next_tick_at = self._next_scheduled_tick()

    async def _baidu_loop(self) -> None:
        while self._enabled and not self._stop_event.is_set():
            if self._next_baidu_tick_at is None:
                self._next_baidu_tick_at = self._next_baidu_slot_tick()
            await self._sleep_or_stop(self._seconds_until(self._next_baidu_tick_at))
            if not self._enabled or self._stop_event.is_set():
                break
            try:
                self._last_baidu_result = await self.run_baidu_slot(
                    scheduled_at=self._next_baidu_tick_at,
                )
            except Exception as exc:
                self._last_baidu_result = {
                    "status": "failed",
                    "error": f"{exc.__class__.__name__}: {str(exc) or '无错误详情'}"[:1000],
                }
                logger.exception("百度全天分片执行失败：{}", exc)
            self._next_baidu_tick_at = self._next_baidu_slot_tick()

    async def run_baidu_slot(self, *, scheduled_at: datetime | None = None) -> dict[str, Any]:
        run_at = scheduled_at or self._now()
        slot_index, slot_count = self._baidu_slot_context(run_at)
        task_uid = f"insight_baidu_slot_{run_at:%Y%m%d}_{slot_index:04d}"
        lock_id = settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID + 1
        async with async_session() as db:
            locked = await self._try_advisory_lock(db, lock_id=lock_id)
            if not locked:
                return {
                    "status": "skipped",
                    "reason": "另一个百度分片调度器实例正在执行",
                    "slot_index": slot_index,
                    "slot_count": slot_count,
                }
            try:
                existing = (
                    await db.exec(select(InsightTask).where(InsightTask.task_uid == task_uid))
                ).first()
                if existing:
                    return {
                        "status": "skipped",
                        "reason": "当前百度时间槽已执行",
                        "task_id": existing.id,
                        "slot_index": slot_index,
                        "slot_count": slot_count,
                    }

                task = InsightTask(
                    task_uid=task_uid,
                    task_type="baidu_spread_tick",
                    status=InsightTaskStatus.RUNNING,
                    progress=10,
                    started_at=self._now(),
                    input_payload={
                        "scheduled_at": run_at.isoformat(),
                        "slot_index": slot_index,
                        "slot_count": slot_count,
                        "slot_interval_seconds": settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS,
                    },
                )
                db.add(task)
                await db.commit()
                await db.refresh(task)
                with collect_llm_usage() as usage_collector:
                    try:
                        result = await insight_monitor_execution_service.run_baidu_discovery_slot(
                            db,
                            slot_index=slot_index,
                            slot_count=slot_count,
                            user_id=settings.INSIGHT_SCHEDULER_USER_ID,
                        )
                        task.status = (
                            InsightTaskStatus.SUCCESS
                            if int(result.get("failed_count") or 0) == 0
                            and int(result.get("circuit_skipped_count") or 0) == 0
                            else InsightTaskStatus.FAILED
                        )
                        task.progress = 100
                        task.finished_at = self._now()
                        task.output_payload = {
                            **result,
                            "token_usage": usage_collector.snapshot(),
                        }
                        task.error_message = next(
                            (
                                str(item.get("error") or "")[:1000]
                                for item in result.get("executions") or []
                                if item.get("status") in {"failed", "circuit_open"}
                            ),
                            None,
                        )
                        db.add(task)
                        await db.commit()
                        return {
                            "status": str(task.status.value),
                            "task_id": task.id,
                            **result,
                        }
                    except Exception as exc:
                        task.status = InsightTaskStatus.FAILED
                        task.progress = 100
                        task.finished_at = self._now()
                        task.error_message = str(exc)[:1000]
                        task.output_payload = {
                            "slot_index": slot_index,
                            "slot_count": slot_count,
                            "error": str(exc)[:1000],
                            "token_usage": usage_collector.snapshot(),
                        }
                        db.add(task)
                        await db.commit()
                        raise
            finally:
                await self._release_advisory_lock(db, lock_id=lock_id)

    def _next_baidu_slot_tick(self) -> datetime:
        interval = max(settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS, 300)
        now = self._now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_seconds = int((now - midnight).total_seconds())
        slot_index = elapsed_seconds // interval
        slot_start = midnight + timedelta(seconds=slot_index * interval)
        jitter_seconds = 15 + ((now.date().toordinal() + slot_index * 17) % 46)
        target = slot_start + timedelta(seconds=jitter_seconds)
        if target <= now:
            slot_index += 1
            slot_start = midnight + timedelta(seconds=slot_index * interval)
            jitter_seconds = 15 + ((slot_start.date().toordinal() + slot_index * 17) % 46)
            target = slot_start + timedelta(seconds=jitter_seconds)
        return target

    def _baidu_slot_context(self, run_at: datetime) -> tuple[int, int]:
        interval = max(settings.INSIGHT_SCHEDULER_BAIDU_SLOT_INTERVAL_SECONDS, 300)
        slot_count = max(86400 // interval, 1)
        midnight = run_at.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_seconds = max(int((run_at - midnight).total_seconds()), 0)
        return min(elapsed_seconds // interval, slot_count - 1), slot_count

    def _now(self) -> datetime:
        return datetime.now(self._timezone()).replace(tzinfo=None)

    def _timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(settings.INSIGHT_SCHEDULER_TIMEZONE)
        except ZoneInfoNotFoundError:
            return ZoneInfo("Asia/Shanghai")

    def _parse_daily_time(self) -> tuple[int, int, int]:
        raw_value = settings.INSIGHT_SCHEDULER_DAILY_TIME.strip()
        parts = raw_value.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError("INSIGHT_SCHEDULER_DAILY_TIME 必须使用 HH:MM 或 HH:MM:SS 格式。")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) == 3 else 0
        except ValueError as exc:
            raise ValueError("INSIGHT_SCHEDULER_DAILY_TIME 只能包含数字和冒号。") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            raise ValueError("INSIGHT_SCHEDULER_DAILY_TIME 超出有效时间范围。")
        return hour, minute, second

    def _next_scheduled_tick(self) -> datetime:
        trigger_mode = settings.INSIGHT_SCHEDULER_TRIGGER_MODE.strip().lower()
        base = self._now()
        if trigger_mode == "fixed_interval":
            delay_seconds = max(settings.INSIGHT_SCHEDULER_STARTUP_DELAY_SECONDS, 0)
            if self._last_tick_at is None:
                return base + timedelta(seconds=delay_seconds)
            return base + timedelta(seconds=settings.INSIGHT_SCHEDULER_INTERVAL_SECONDS)
        hour, minute, second = self._parse_daily_time()
        scheduled = base.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if scheduled <= base:
            scheduled += timedelta(days=1)
        return scheduled

    def _seconds_until(self, target: datetime) -> float:
        return max((target - self._now()).total_seconds(), 0.0)

    async def _sleep_or_stop(self, seconds: float) -> None:
        if seconds <= 0:
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _try_advisory_lock(self, db, *, lock_id: int | None = None) -> bool:
        result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id or settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )
        return bool(result.scalar_one())

    async def _release_advisory_lock(self, db, *, lock_id: int | None = None) -> None:
        await db.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": lock_id or settings.INSIGHT_SCHEDULER_ADVISORY_LOCK_ID},
        )


insight_scheduler_service = InsightSchedulerService()
