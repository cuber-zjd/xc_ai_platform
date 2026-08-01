import asyncio
import random
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.logger import logger
from app.db.session import async_session
from app.models.agent.insight import InsightChannel, InsightCompany, InsightMonitorConfig
from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest
from app.schemas.agent.insight.data_source import InsightDataSourceScheduleExecution, InsightDataSourceScheduleRunResponse
from app.services.agent.insight.crawler.channel_adapter_service import insight_channel_adapter_service
from app.services.agent.insight.crawler import insight_search_discovery_service
from app.services.agent.insight.crawler.search_client import InsightSearchHit, bocha_search_client, doubao_web_search_client


@dataclass(slots=True)
class MonitorChannelPlanItem:
    channel: InsightChannel
    action: str
    reason: str
    tier: str
    cost_level: str
    trigger_mode: str
    handler_code: str | None
    max_results: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel.id,
            "channel_code": self.channel.channel_code,
            "channel_name": self.channel.channel_name,
            "action": self.action,
            "reason": self.reason,
            "tier": self.tier,
            "cost_level": self.cost_level,
            "trigger_mode": self.trigger_mode,
            "handler_code": self.handler_code,
            "max_results": self.max_results,
        }


@dataclass(slots=True)
class MonitorCollectionPlan:
    query: str
    items: list[MonitorChannelPlanItem]
    budget: dict[str, Any]

    def executable_items(self) -> list[MonitorChannelPlanItem]:
        return [item for item in self.items if item.action == "execute" and item.handler_code]

    def conditional_items(self) -> list[MonitorChannelPlanItem]:
        return [item for item in self.items if item.action == "conditional" and item.handler_code]

    def skipped_items(self) -> list[MonitorChannelPlanItem]:
        return [item for item in self.items if item.action not in {"execute", "conditional"}]

    def summary(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        by_tier: dict[str, int] = {}
        for item in self.items:
            by_action[item.action] = by_action.get(item.action, 0) + 1
            by_tier[item.tier] = by_tier.get(item.tier, 0) + 1
        return {
            "query": self.query,
            "planned_channel_count": len(self.items),
            "execute_now_count": len(self.executable_items()),
            "conditional_count": len(self.conditional_items()),
            "skipped_count": len(self.skipped_items()),
            "by_action": by_action,
            "by_tier": by_tier,
            "budget": self.budget,
            "items": [item.to_dict() for item in self.items[:80]],
        }


@dataclass(slots=True)
class GroupedDiscoveryBatch:
    group_key: str
    group_name: str
    rows: list[InsightMonitorConfig]
    query: str


class InsightMonitorExecutionService:
    """按监测配置执行采集，不再把旧数据源作为调度主表。"""

    supported_search_channel_codes = {
        "baidu_news": "baidu_news",
        "bocha_search": "bocha",
        "doubao_web_search": "doubao_web_search",
    }
    default_search_channel_order = ("baidu_news", "bocha_search", "doubao_web_search")
    free_discovery_channel_codes = {"baidu_news"}
    paid_discovery_channel_codes = {"bocha_search"}
    ai_discovery_channel_codes = {"doubao_web_search"}
    scenario_modules = (
        "企业新闻",
        "官网动态",
        "经营财经",
        "专利技术",
        "电商新品",
        "行业资讯",
        "政策监管",
        "技术专利",
        "综合舆情",
    )
    # 单个监测对象会为每个渠道占用独立数据库会话；并发需给 API、前端和正文补抓预留连接。
    api_concurrency = 3
    playwright_concurrency = 2
    grouped_search_concurrency = 3
    grouped_ai_search_concurrency = 2
    channel_timeout_seconds = 180

    async def run_daily_discovery_all(
        self,
        db: AsyncSession,
        *,
        user_id: int | None = None,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> dict[str, Any]:
        """每日覆盖全部监测对象，百度逐对象发现，博查和豆包按对象组补充。"""

        filters = [
            InsightMonitorConfig.is_deleted == 0,
            InsightMonitorConfig.status == "active",
            InsightMonitorConfig.schedule_enabled == True,  # noqa: E712
            InsightMonitorConfig.fetch_frequency != "manual",
        ]
        rows = list(
            (
                await db.exec(
                    select(InsightMonitorConfig)
                    .where(*filters)
                    .order_by(InsightMonitorConfig.id.asc())
                )
            ).all()
        )
        row_ids = [row.id for row in rows if row.id]
        if not rows:
            return {
                "checked_count": 0,
                "baidu_attempted_count": 0,
                "baidu_success_count": 0,
                "baidu_failed_count": 0,
                "grouped_batch_count": 0,
                "grouped_failed_count": 0,
                "hit_count": 0,
                "candidate_count": 0,
                "signal_monitor_config_ids": [],
                "errors": [],
            }

        channels = {channel.channel_code: channel for channel in await self._active_channels(db)}
        baidu_channel = channels.get("baidu_news")
        freshness = freshness_override or settings.INSIGHT_SCHEDULER_DAILY_DISCOVERY_FRESHNESS
        company_ids = {
            int(row.object_id)
            for row in rows
            if row.object_type == "company" and row.object_id is not None
        }
        companies = (
            list((await db.exec(select(InsightCompany).where(InsightCompany.id.in_(company_ids)))).all())
            if company_ids
            else []
        )
        company_by_id = {company.id: company for company in companies if company.id}
        prepared_queries: dict[int, str] = {}
        for row in rows:
            if row.id:
                prepared_queries[row.id] = self._build_query_parts(row, company_by_id.get(row.object_id))

        semaphore = asyncio.Semaphore(max(1, settings.INSIGHT_SCHEDULER_BAIDU_CONCURRENCY))
        baidu_logs: list[dict[str, Any]] = []

        async def run_baidu(row: InsightMonitorConfig) -> dict[str, Any]:
            if not row.id or not baidu_channel or not baidu_channel.id:
                return {
                    "monitor_config_id": row.id,
                    "status": "skipped",
                    "error": "百度资讯渠道未启用",
                    "hits": 0,
                    "candidates": 0,
                }
            async with semaphore:
                try:
                    response = await asyncio.wait_for(
                        self._execute_search_channel_in_new_session(
                            row_id=row.id,
                            channel_id=baidu_channel.id,
                            query=prepared_queries.get(row.id) or row.object_name or row.config_name,
                            handler_code="baidu_news",
                            max_results=min(10, self._frequency_max_results(row.fetch_frequency)),
                            user_id=user_id,
                            freshness_override=freshness,
                            published_start=published_start,
                            published_end=published_end,
                        ),
                        timeout=self.channel_timeout_seconds,
                    )
                    return {
                        "monitor_config_id": row.id,
                        "status": "success",
                        "hits": len(response.hits),
                        "candidates": len(response.candidates),
                    }
                except Exception as exc:
                    return {
                        "monitor_config_id": row.id,
                        "status": "failed",
                        "error": f"{exc.__class__.__name__}: {str(exc) or '无错误详情'}"[:500],
                        "hits": 0,
                        "candidates": 0,
                    }
                finally:
                    cooldown_min = max(0.0, settings.INSIGHT_SCHEDULER_BAIDU_COOLDOWN_MIN_SECONDS)
                    cooldown_max = max(cooldown_min, settings.INSIGHT_SCHEDULER_BAIDU_COOLDOWN_MAX_SECONDS)
                    if cooldown_max > 0:
                        await asyncio.sleep(random.uniform(cooldown_min, cooldown_max))

        if baidu_channel:
            baidu_logs = [
                await task
                for task in asyncio.as_completed([asyncio.create_task(run_baidu(row)) for row in rows])
            ]
        else:
            baidu_logs = [await run_baidu(row) for row in rows]

        grouped_summary = await self._execute_grouped_daily_discovery(
            db,
            row_ids,
            user_id=user_id,
            freshness_override=freshness,
            published_start=published_start,
            published_end=published_end,
        )
        grouped_logs = list(grouped_summary.get("batches") or [])
        grouped_by_monitor = grouped_summary.get("by_monitor_config_id") or {}
        daily_adapter_summary = await self._execute_daily_key_channel_sweep(
            db,
            rows,
            user_id=user_id,
            freshness_override=freshness,
            published_start=published_start,
            published_end=published_end,
        )
        daily_adapter_logs = list(daily_adapter_summary.get("runs") or [])
        daily_adapter_by_monitor = daily_adapter_summary.get("by_monitor_config_id") or {}
        signal_ids = {
            int(item["monitor_config_id"])
            for item in baidu_logs
            if item.get("monitor_config_id") and (item.get("hits", 0) > 0 or item.get("candidates", 0) > 0)
        }
        signal_ids.update(
            int(row_id)
            for row_id, counts in grouped_by_monitor.items()
            if int(counts.get("hits") or 0) > 0 or int(counts.get("candidates") or 0) > 0
        )
        signal_ids.update(
            int(row_id)
            for row_id, counts in daily_adapter_by_monitor.items()
            if int(counts.get("hits") or 0) > 0 or int(counts.get("candidates") or 0) > 0
        )
        grouped_hit_count = sum(int(item.get("hits") or 0) for item in grouped_logs)
        grouped_candidate_count = sum(int(item.get("candidates") or 0) for item in grouped_logs)
        daily_adapter_hit_count = sum(int(item.get("hits") or 0) for item in daily_adapter_logs)
        daily_adapter_candidate_count = sum(
            int(item.get("candidates") or 0) for item in daily_adapter_logs
        )
        return {
            "checked_count": len(rows),
            "baidu_attempted_count": len(rows) if baidu_channel else 0,
            "baidu_success_count": sum(1 for item in baidu_logs if item.get("status") == "success"),
            "baidu_failed_count": sum(1 for item in baidu_logs if item.get("status") == "failed"),
            "grouped_batch_count": len(grouped_logs),
            "grouped_failed_count": sum(1 for item in grouped_logs if item.get("status") != "success"),
            "grouped_partial_count": sum(1 for item in grouped_logs if item.get("status") == "partial"),
            "grouped_retry_count": sum(int(item.get("retry_count") or 0) for item in grouped_logs),
            "daily_adapter_run_count": len(daily_adapter_logs),
            "daily_adapter_success_count": sum(
                1 for item in daily_adapter_logs if item.get("status") == "success"
            ),
            "daily_adapter_failed_count": sum(
                1 for item in daily_adapter_logs if item.get("status") == "failed"
            ),
            "daily_adapter_channel_count": len(
                {str(item.get("channel_code")) for item in daily_adapter_logs}
            ),
            "fulltext_summary": {
                "success": sum(int((item.get("fulltext_summary") or {}).get("success") or 0) for item in grouped_logs),
                "failed": sum(int((item.get("fulltext_summary") or {}).get("failed") or 0) for item in grouped_logs),
                "skipped": sum(int((item.get("fulltext_summary") or {}).get("skipped") or 0) for item in grouped_logs),
                "not_attempted": sum(
                    int((item.get("fulltext_summary") or {}).get("not_attempted") or 0)
                    for item in grouped_logs
                ),
            },
            "hit_count": (
                sum(int(item.get("hits") or 0) for item in baidu_logs)
                + grouped_hit_count
                + daily_adapter_hit_count
            ),
            "candidate_count": sum(int(item.get("candidates") or 0) for item in baidu_logs)
            + grouped_candidate_count
            + daily_adapter_candidate_count,
            "signal_monitor_config_ids": sorted(signal_ids),
            "errors": [item for item in baidu_logs if item.get("status") == "failed"][:50]
            + [item for item in grouped_logs if item.get("status") != "success"][:50]
            + [item for item in daily_adapter_logs if item.get("status") == "failed"][:50],
            "grouped_batches": grouped_logs,
            "daily_adapter_runs": daily_adapter_logs,
        }

    async def run_due_monitor_configs(
        self,
        db: AsyncSession,
        *,
        limit: int = 5,
        user_id: int | None = None,
        freshness_override: str | None = None,
        priority_row_ids: list[int] | None = None,
    ) -> InsightDataSourceScheduleRunResponse:
        limit = min(max(limit, 1), 50)
        now = datetime.now()
        active_filters = [
            InsightMonitorConfig.is_deleted == 0,
            InsightMonitorConfig.status == "active",
            InsightMonitorConfig.schedule_enabled == True,  # noqa: E712
            InsightMonitorConfig.fetch_frequency != "manual",
        ]
        due_filters = [
            *active_filters,
            or_(InsightMonitorConfig.next_run_time == None, InsightMonitorConfig.next_run_time <= now),  # noqa: E711
        ]
        checked_count = (
            await db.exec(select(func.count()).select_from(InsightMonitorConfig).where(*active_filters))
        ).one()
        due_count = (await db.exec(select(func.count()).select_from(InsightMonitorConfig).where(*due_filters))).one()
        priority_ids = {int(item) for item in priority_row_ids or []}
        candidate_filters = [
            *active_filters,
            or_(
                InsightMonitorConfig.next_run_time == None,  # noqa: E711
                InsightMonitorConfig.next_run_time <= now,
                InsightMonitorConfig.id.in_(priority_ids) if priority_ids else False,
            ),
        ]
        candidate_rows = list(
            (
                await db.exec(
                    select(InsightMonitorConfig)
                    .where(*candidate_filters)
                    .order_by(InsightMonitorConfig.next_run_time.asc().nullsfirst(), InsightMonitorConfig.id.asc())
                )
            ).all()
        )
        candidate_rows.sort(
            key=lambda item: (
                0 if item.id in priority_ids else 1,
                item.next_run_time or datetime.min,
                item.id or 0,
            )
        )
        rows = candidate_rows[:limit]

        executions: list[InsightDataSourceScheduleExecution] = []
        for row in rows:
            row.last_schedule_status = "running"
            row.last_schedule_message = "监测配置采集中"
            row.last_fetch_time = datetime.now()
            row.update_time = datetime.now()
            await db.commit()
            try:
                result = await asyncio.wait_for(
                    self.execute_monitor_config(
                        db,
                        row,
                        user_id=user_id,
                        include_conditional_discovery=False,
                        include_discovery_channels=False,
                        include_daily_sweep_channels=False,
                        freshness_override=freshness_override,
                    ),
                    timeout=self._timeout_seconds(row),
                )
                found_count = sum(len(item.hits) for item in result.get("search_results", []))
                candidate_count = sum(len(item.candidates) for item in result.get("search_results", []))
                executed_channel_count = int(result.get("executed_channel_count") or 0)
                skipped_channel_count = int(result.get("skipped_channel_count") or 0)
                planned_channel_count = int(result.get("planned_channel_count") or 0)
                paid_channel_call_count = int(result.get("paid_channel_call_count") or 0)
                ai_search_call_count = int(result.get("ai_search_call_count") or 0)
                plan_summary = result.get("collection_plan")
                row.last_schedule_status = "success"
                row.last_schedule_message = (
                    f"计划 {planned_channel_count} 个渠道，执行 {executed_channel_count} 个，"
                    f"博查补充 {paid_channel_call_count} 次，AI 联网补充 {ai_search_call_count} 次，"
                    f"跳过/暂缓 {skipped_channel_count} 个；"
                    f"发现 {found_count} 条，候选 {candidate_count} 条"
                )
                row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.config_json, datetime.now())
                row.last_success_time = datetime.now()
                row.consecutive_failure_count = 0
                row.last_failure_time = None
                row.auto_paused_reason = None
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
                await db.commit()
                executions.append(
                    InsightDataSourceScheduleExecution(
                        monitor_config_id=row.id,
                        source_name=row.config_name,
                        status="success",
                        message=row.last_schedule_message,
                        next_run_time=row.next_run_time,
                        found_count=found_count,
                        candidate_count=candidate_count,
                        planned_channel_count=planned_channel_count,
                        executed_channel_count=executed_channel_count,
                        skipped_channel_count=skipped_channel_count,
                        paid_channel_call_count=paid_channel_call_count,
                        plan_summary=plan_summary,
                    )
                )
            except Exception as exc:
                row.last_schedule_status = "failed"
                row.last_schedule_message = str(exc)[:1000]
                row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.config_json, datetime.now())
                row.consecutive_failure_count = (row.consecutive_failure_count or 0) + 1
                row.last_failure_time = datetime.now()
                if row.consecutive_failure_count >= settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD:
                    row.schedule_enabled = False
                    row.next_run_time = None
                    row.last_schedule_status = "paused"
                    row.auto_paused_reason = (
                        f"连续失败 {row.consecutive_failure_count} 次，已自动暂停监测配置。最近错误：{str(exc)[:700]}"
                    )[:1000]
                    row.last_schedule_message = row.auto_paused_reason
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
                await db.commit()
                executions.append(
                    InsightDataSourceScheduleExecution(
                        monitor_config_id=row.id,
                        source_name=row.config_name,
                        status="failed",
                        message=row.last_schedule_message,
                        next_run_time=row.next_run_time,
                    )
                )

        failed_count = sum(1 for item in executions if item.status == "failed")
        return InsightDataSourceScheduleRunResponse(
            checked_count=checked_count,
            due_count=due_count,
            executed_count=len(executions) - failed_count,
            failed_count=failed_count,
            executions=executions,
        )

    async def execute_monitor_config(
        self,
        db: AsyncSession,
        row: InsightMonitorConfig,
        *,
        user_id: int | None,
        include_conditional_discovery: bool = True,
        include_discovery_channels: bool = True,
        include_daily_sweep_channels: bool = True,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> dict[str, Any]:
        channels = await self._active_channels(db)
        query = await self._build_query(db, row)
        plan = self._build_collection_plan(
            row,
            channels,
            query,
            include_discovery_channels=include_discovery_channels,
            include_daily_sweep_channels=include_daily_sweep_channels,
        )
        if not plan.items:
            raise ValueError("当前监测配置没有匹配到可用渠道源")
        if not include_discovery_channels and not plan.executable_items() and not plan.conditional_items():
            return {
                "search_results": [],
                "query": query,
                "collection_plan": plan.summary(),
                "planned_channel_count": len(plan.items),
                "covered_channel_count": len(plan.items),
                "executed_channel_count": 0,
                "skipped_channel_count": len(plan.items),
                "paid_channel_call_count": 0,
                "ai_search_call_count": 0,
                "executed_channels": [],
                "skipped_channels": [item.to_dict() for item in plan.items[:50]],
                "channel_errors": [],
            }

        search_results: list[Any] = []
        skipped_channels = [item.to_dict() for item in plan.skipped_items()]
        executed_channels: list[dict[str, Any]] = []
        channel_errors: list[dict[str, Any]] = []
        paid_channel_call_count = 0

        executable_results = await self._execute_plan_items_concurrently(
            row_id=row.id or 0,
            items=plan.executable_items(),
            query=query,
            user_id=user_id,
            freshness_override=freshness_override,
            published_start=published_start,
            published_end=published_end,
        )
        for item, result, exc in executable_results:
            if exc:
                error_item = item.to_dict() | {"error": str(exc)[:500]}
                channel_errors.append(error_item)
                skipped_channels.append(error_item | {"reason": f"执行失败：{str(exc)[:200]}"})
                continue
            if result:
                search_results.append(result)
                executed_channels.append(item.to_dict())

        should_run_paid_search = include_conditional_discovery and self._should_run_paid_discovery(row, search_results, channel_errors)
        should_run_ai_search = self._should_run_ai_discovery(row, search_results, channel_errors)
        paid_budget = int(plan.budget.get("paid_search_calls_per_run") or 0)
        ai_search_budget = int(plan.budget.get("ai_search_calls_per_run") or 0)
        conditional_to_run: list[MonitorChannelPlanItem] = []
        ai_search_call_count = 0
        if not include_conditional_discovery:
            for item in plan.conditional_items():
                skipped_channels.append(item.to_dict() | {"reason": "周期调度中由每日分组搜索统一补充"})
        conditional_items = plan.conditional_items() if include_conditional_discovery else []
        for item in conditional_items:
            if item.channel.channel_code in self.paid_discovery_channel_codes and not should_run_paid_search:
                skipped_channels.append(item.to_dict() | {"reason": "本轮策略判断可暂缓付费补充源"})
                continue
            if item.channel.channel_code in self.paid_discovery_channel_codes and paid_channel_call_count >= paid_budget:
                skipped_channels.append(item.to_dict() | {"reason": "本轮付费搜索预算已用完"})
                continue
            if item.channel.channel_code in self.ai_discovery_channel_codes and not should_run_ai_search:
                skipped_channels.append(item.to_dict() | {"reason": "基础发现已有足够线索，本轮暂缓 AI 联网补充"})
                continue
            if item.channel.channel_code in self.ai_discovery_channel_codes and ai_search_call_count >= ai_search_budget:
                skipped_channels.append(item.to_dict() | {"reason": "本轮 AI 联网搜索预算已用完"})
                continue
            conditional_to_run.append(item)
            if item.channel.channel_code in self.paid_discovery_channel_codes:
                paid_channel_call_count += 1
            if item.channel.channel_code in self.ai_discovery_channel_codes:
                ai_search_call_count += 1

        conditional_results = await self._execute_plan_items_concurrently(
            row_id=row.id or 0,
            items=conditional_to_run,
            query=query,
            user_id=user_id,
            freshness_override=freshness_override,
            published_start=published_start,
            published_end=published_end,
        )
        for item, result, exc in conditional_results:
            if exc:
                error_item = item.to_dict() | {"error": str(exc)[:500]}
                channel_errors.append(error_item)
                skipped_channels.append(error_item | {"reason": f"执行失败：{str(exc)[:200]}"})
                continue
            if result:
                search_results.append(result)
                executed_channels.append(item.to_dict())

        if not search_results:
            message = "当前监测配置没有成功执行的渠道"
            if channel_errors:
                message += f"：{channel_errors[0].get('error')}"
            raise ValueError(message)
        return {
            "search_results": search_results,
            "query": query,
            "collection_plan": plan.summary(),
            "planned_channel_count": len(plan.items),
            "covered_channel_count": len(plan.items),
            "executed_channel_count": len(search_results),
            "skipped_channel_count": len(skipped_channels),
            "paid_channel_call_count": paid_channel_call_count,
            "ai_search_call_count": ai_search_call_count,
            "executed_channels": executed_channels,
            "skipped_channels": skipped_channels[:50],
            "channel_errors": channel_errors[:20],
        }

    async def _execute_daily_key_channel_sweep(
        self,
        db: AsyncSession,
        rows: list[InsightMonitorConfig],
        *,
        user_id: int | None,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> dict[str, Any]:
        configured_codes = self._daily_adapter_channel_codes()
        if not configured_codes:
            return {"by_monitor_config_id": {}, "runs": []}

        supported_codes = insight_channel_adapter_service.supported_channel_codes()
        channels = [
            channel
            for channel in await self._active_channels(db)
            if channel.channel_code in configured_codes
            and channel.channel_code in supported_codes
            and (channel.default_frequency or "").strip().lower() == "daily"
        ]
        topic_rows = [
            row
            for row in rows
            if row.id
            and row.object_type != "company"
            and row.schedule_enabled
            and not self._is_placeholder_monitor(row)
            and any(str(keyword).strip() for keyword in row.keywords or [])
        ]
        if not channels or not topic_rows:
            return {"by_monitor_config_id": {}, "runs": []}

        high_coverage_codes = self._csv_setting(
            settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_HIGH_COVERAGE_CODES
        )
        playwright_semaphore = asyncio.Semaphore(
            max(1, settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CONCURRENCY)
        )
        http_semaphore = asyncio.Semaphore(max(1, self.api_concurrency))
        channel_locks = {channel.channel_code: asyncio.Lock() for channel in channels}
        by_monitor: dict[int, dict[str, int]] = defaultdict(
            lambda: {"hits": 0, "candidates": 0}
        )

        async def run_one(
            row: InsightMonitorConfig,
            channel: InsightChannel,
        ) -> dict[str, Any]:
            definition = insight_channel_adapter_service.definition_for(channel.channel_code)
            semaphore = (
                http_semaphore
                if definition and definition.adapter_kind == "http"
                else playwright_semaphore
            )
            query = self._daily_adapter_query(row, channel)
            started_at = datetime.now()
            async with channel_locks[channel.channel_code]:
                async with semaphore:
                    try:
                        response = await asyncio.wait_for(
                            self._execute_search_channel_in_new_session(
                                row_id=row.id or 0,
                                channel_id=channel.id or 0,
                                query=query,
                                handler_code=channel.channel_code,
                                max_results=min(
                                    10,
                                    self._frequency_max_results(row.fetch_frequency),
                                ),
                                user_id=user_id,
                                freshness_override=freshness_override,
                                published_start=published_start,
                                published_end=published_end,
                            ),
                            timeout=max(
                                settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_TIMEOUT_SECONDS,
                                60,
                            ),
                        )
                    except Exception as exc:
                        return {
                            "channel_code": channel.channel_code,
                            "channel_name": channel.channel_name,
                            "monitor_config_id": row.id,
                            "monitor_config_name": row.config_name,
                            "query": query,
                            "status": "failed",
                            "hits": 0,
                            "candidates": 0,
                            "duration_ms": int(
                                (datetime.now() - started_at).total_seconds() * 1000
                            ),
                            "error": (
                                f"{exc.__class__.__name__}: "
                                f"{str(exc) or '渠道请求失败或超时'}"
                            )[:500],
                        }

            hit_count = len(response.hits)
            candidate_count = len(response.candidates)
            if row.id:
                by_monitor[row.id]["hits"] += hit_count
                by_monitor[row.id]["candidates"] += candidate_count
            return {
                "channel_code": channel.channel_code,
                "channel_name": channel.channel_name,
                "monitor_config_id": row.id,
                "monitor_config_name": row.config_name,
                "query": query,
                "status": "success",
                "hits": hit_count,
                "candidates": candidate_count,
                "duration_ms": int(
                    (datetime.now() - started_at).total_seconds() * 1000
                ),
            }

        tasks: list[asyncio.Task] = []
        for channel in channels:
            topic_limit = (
                len(topic_rows)
                if channel.channel_code in high_coverage_codes
                else max(1, settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_TOPIC_LIMIT)
            )
            selected_rows = self._select_daily_adapter_monitors(
                channel,
                topic_rows,
                topic_limit,
            )
            tasks.extend(
                asyncio.create_task(run_one(row, channel)) for row in selected_rows
            )

        run_logs = [await task for task in asyncio.as_completed(tasks)] if tasks else []
        return {
            "by_monitor_config_id": {
                str(row_id): counts for row_id, counts in by_monitor.items()
            },
            "runs": run_logs,
        }

    def _daily_adapter_channel_codes(self) -> set[str]:
        return self._csv_setting(settings.INSIGHT_SCHEDULER_DAILY_ADAPTER_CHANNEL_CODES)

    def _csv_setting(self, value: str | None) -> set[str]:
        return {
            item.strip().lower()
            for item in str(value or "").split(",")
            if item.strip()
        }

    def _select_daily_adapter_monitors(
        self,
        channel: InsightChannel,
        rows: list[InsightMonitorConfig],
        limit: int,
    ) -> list[InsightMonitorConfig]:
        scenarios = {
            str(item).strip()
            for item in channel.applicable_scenarios or []
            if str(item).strip()
        }
        matching = [
            row
            for row in rows
            if scenarios.intersection(
                {
                    str(module).strip()
                    for module in row.enabled_modules or []
                    if str(module).strip()
                }
            )
        ]
        remaining = [row for row in rows if row not in matching]
        seed = (
            datetime.now().date().toordinal()
            + int(channel.id or sum(ord(char) for char in channel.channel_code))
        )

        def rotate(items: list[InsightMonitorConfig]) -> list[InsightMonitorConfig]:
            if not items:
                return []
            offset = seed % len(items)
            return items[offset:] + items[:offset]

        candidates = rotate(matching) + rotate(remaining)
        if not candidates:
            return []
        return candidates[: min(max(1, limit), len(candidates))]

    def _daily_adapter_query(
        self,
        row: InsightMonitorConfig,
        channel: InsightChannel,
    ) -> str:
        keywords = [
            str(item).strip()
            for item in row.keywords or []
            if str(item).strip()
        ]
        if not keywords:
            return str(row.object_name or row.config_name).strip()
        offset = (
            datetime.now().date().toordinal()
            + int(channel.id or 0)
            + int(row.id or 0)
        ) % len(keywords)
        return keywords[offset]

    async def _execute_grouped_daily_discovery(
        self,
        db: AsyncSession,
        row_ids: list[int],
        *,
        user_id: int | None,
        freshness_override: str | None = None,
        channel_codes: set[str] | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> dict[str, Any]:
        if not row_ids:
            return {"by_monitor_config_id": {}, "batches": []}
        rows = list(
            (
                await db.exec(
                    select(InsightMonitorConfig)
                    .where(
                        InsightMonitorConfig.id.in_(row_ids),
                        InsightMonitorConfig.is_deleted == 0,
                        InsightMonitorConfig.status == "active",
                    )
                    .order_by(InsightMonitorConfig.id.asc())
                )
            ).all()
        )
        if not rows:
            return {"by_monitor_config_id": {}, "batches": []}

        channels = {channel.channel_code: channel for channel in await self._active_channels(db)}
        enabled_grouped_channels = channel_codes or {"bocha_search", "doubao_web_search"}
        bocha_channel = channels.get("bocha_search") if "bocha_search" in enabled_grouped_channels else None
        doubao_channel = (
            channels.get("doubao_web_search") if "doubao_web_search" in enabled_grouped_channels else None
        )
        if not bocha_channel and not doubao_channel:
            return {"by_monitor_config_id": {}, "batches": []}

        bocha_batches = (
            self._build_grouped_discovery_batches(
                rows,
                batch_size=max(2, settings.INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE),
            )
            if bocha_channel
            else []
        )
        doubao_batches = (
            self._build_grouped_discovery_batches(
                rows,
                batch_size=max(1, settings.INSIGHT_SCHEDULER_GROUPED_AI_BATCH_SIZE),
            )
            if doubao_channel
            else []
        )
        by_monitor: dict[int, dict[str, int]] = defaultdict(lambda: {"hits": 0, "candidates": 0})
        batch_logs: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.grouped_search_concurrency)
        ai_semaphore = asyncio.Semaphore(self.grouped_ai_search_concurrency)
        ai_retry_semaphore = asyncio.Semaphore(
            max(1, settings.INSIGHT_SCHEDULER_GROUPED_AI_RETRY_CONCURRENCY)
        )
        ingest_semaphore = asyncio.Semaphore(
            max(settings.INSIGHT_SCHEDULER_GROUPED_INGEST_CONCURRENCY, 1)
        )

        async def run_one(
            batch: GroupedDiscoveryBatch,
            channel: InsightChannel,
            handler_code: str,
            freshness: str | None,
        ) -> dict[str, Any]:
            current_semaphore = ai_semaphore if handler_code == "doubao_web_search" else semaphore
            async with current_semaphore:
                try:
                    raw_hits, search_meta = await self._search_grouped_channel_with_retry(
                        batch,
                        handler_code,
                        freshness_override=freshness,
                        retry_semaphore=ai_retry_semaphore,
                    )
                except Exception as exc:
                    return {
                        "group_key": batch.group_key,
                        "channel_code": channel.channel_code,
                        "query": batch.query,
                        "status": "failed",
                        "error": f"{exc.__class__.__name__}: {str(exc) or '渠道请求超时或未返回'}"[:500],
                        "retry_count": 1 if handler_code == "doubao_web_search" else 0,
                    }

            assigned = self._assign_grouped_hits(batch.rows, raw_hits)
            hit_count = 0
            candidate_count = 0
            ingest_errors: list[dict[str, Any]] = []
            fulltext_summary = {"success": 0, "failed": 0, "skipped": 0, "not_attempted": 0}
            for row, hits in assigned.values():
                if not hits or not row.id:
                    continue
                request = InsightSearchDiscoveryRequest(
                    query=batch.query,
                    channels=[handler_code],
                    freshness=freshness or self._freshness_for_frequency(row.fetch_frequency),
                    published_start=published_start,
                    published_end=published_end,
                    max_results=min(max(len(hits), 1), self._frequency_max_results(row.fetch_frequency)),
                    crawl_top_n=0,
                    enrich_fulltext_before_review=settings.INSIGHT_REVIEW_FULLTEXT_REQUIRED,
                    fulltext_top_n=max(settings.INSIGHT_REVIEW_FULLTEXT_TOP_N, 0),
                    monitor_config_id=row.id,
                    source_channel_id=channel.id,
                    include_keywords=[],
                    exclude_keywords=row.excluded_keywords or [],
                    filter_prompt=self._filter_prompt(row, channel),
                    enable_llm_filter=True,
                    llm_min_score=0.45,
                    create_candidate_from_hits=True,
                    run_type=self._run_type(row),
                )
                try:
                    async with ingest_semaphore:
                        async with async_session() as ingest_db:
                            response = await insight_search_discovery_service.ingest_search_hits(
                                ingest_db,
                                request,
                                hits,
                                user_id=user_id,
                                is_admin=True,
                            )
                except Exception as exc:
                    ingest_errors.append(
                        {
                            "monitor_config_id": row.id,
                            "config_name": row.config_name,
                            "error": f"{exc.__class__.__name__}: {str(exc) or '无错误详情'}"[:500],
                        }
                    )
                    continue
                row_hit_count = len(response.hits)
                row_candidate_count = len(response.candidates)
                hit_count += row_hit_count
                candidate_count += row_candidate_count
                response_fulltext = (response.task.output_payload or {}).get("fulltext_summary") or {}
                for key in fulltext_summary:
                    fulltext_summary[key] += int(response_fulltext.get(key) or 0)
                by_monitor[row.id]["hits"] += row_hit_count
                by_monitor[row.id]["candidates"] += row_candidate_count
            search_errors = list(search_meta.get("retry_errors") or [])
            return {
                "group_key": batch.group_key,
                "group_name": batch.group_name,
                "channel_code": channel.channel_code,
                "query": batch.query,
                "status": "partial" if ingest_errors or search_errors else "success",
                "raw_hits": len(raw_hits),
                "assigned_monitor_count": len(assigned),
                "hits": hit_count,
                "candidates": candidate_count,
                "ingest_errors": ingest_errors[:20],
                "retry_count": int(search_meta.get("retry_count") or 0),
                "retry_errors": search_errors[:10],
                "fulltext_summary": fulltext_summary,
            }

        tasks: list[asyncio.Task] = []
        if bocha_channel:
            tasks.extend(
                asyncio.create_task(run_one(batch, bocha_channel, "bocha", freshness_override))
                for batch in bocha_batches
            )
        if doubao_channel:
            tasks.extend(
                asyncio.create_task(
                    run_one(batch, doubao_channel, "doubao_web_search", freshness_override)
                )
                for batch in doubao_batches
            )
        if tasks:
            batch_logs = [await task for task in asyncio.as_completed(tasks)]

        if by_monitor:
            async with async_session() as status_db:
                for row_id, counts in by_monitor.items():
                    row = await status_db.get(InsightMonitorConfig, row_id)
                    if not row:
                        continue
                    suffix = f"；分组搜索补充发现 {counts['hits']} 条，候选 {counts['candidates']} 条"
                    row.last_schedule_message = f"{row.last_schedule_message or ''}{suffix}"[:1000]
                    row.update_time = datetime.now()
                    status_db.add(row)
                await status_db.commit()

        return {
            "by_monitor_config_id": {str(key): value for key, value in by_monitor.items()},
            "batches": batch_logs,
        }

    async def _search_grouped_channel_with_retry(
        self,
        batch: GroupedDiscoveryBatch,
        handler_code: str,
        *,
        freshness_override: str | None = None,
        retry_semaphore: asyncio.Semaphore | None = None,
    ) -> tuple[list[InsightSearchHit], dict[str, Any]]:
        timeout = (
            max(settings.INSIGHT_SCHEDULER_GROUPED_AI_TIMEOUT_SECONDS, 30)
            if handler_code == "doubao_web_search"
            else self.channel_timeout_seconds
        )
        try:
            hits = await asyncio.wait_for(
                self._search_grouped_channel(batch, handler_code, freshness_override=freshness_override),
                timeout=timeout,
            )
            return hits, {"retry_count": 0, "retry_errors": []}
        except Exception as exc:
            if handler_code != "doubao_web_search" or len(batch.rows) <= 1:
                raise
            logger.warning(
                "Insight 豆包分组搜索首次失败，准备拆分重试: group_key={} rows={} error={}",
                batch.group_key,
                len(batch.rows),
                f"{exc.__class__.__name__}: {str(exc) or '请求超时'}"[:300],
            )

        configured_batch_size = max(1, settings.INSIGHT_SCHEDULER_GROUPED_AI_RETRY_BATCH_SIZE)
        retry_batch_size = min(configured_batch_size, max(1, len(batch.rows) // 2))
        retry_batches: list[GroupedDiscoveryBatch] = []
        for index in range(0, len(batch.rows), retry_batch_size):
            retry_rows = batch.rows[index : index + retry_batch_size]
            retry_batches.append(
                GroupedDiscoveryBatch(
                    group_key=f"{batch.group_key}:retry:{index // retry_batch_size + 1}",
                    group_name=self._group_name(retry_rows),
                    rows=retry_rows,
                    query=self._build_group_query(retry_rows),
                )
            )
        shared_retry_semaphore = retry_semaphore or asyncio.Semaphore(
            max(1, settings.INSIGHT_SCHEDULER_GROUPED_AI_RETRY_CONCURRENCY)
        )

        async def run_retry(
            retry_batch: GroupedDiscoveryBatch,
        ) -> tuple[list[InsightSearchHit], dict[str, Any] | None]:
            try:
                async with shared_retry_semaphore:
                    hits = await asyncio.wait_for(
                        self._search_grouped_channel(
                            retry_batch,
                            handler_code,
                            freshness_override=freshness_override,
                        ),
                        timeout=timeout,
                    )
                return hits, None
            except Exception as exc:
                return [], {
                        "group_key": retry_batch.group_key,
                        "query": retry_batch.query,
                        "error": f"{exc.__class__.__name__}: {str(exc) or '重试未返回'}"[:500],
                    }

        retry_results = await asyncio.gather(*(run_retry(item) for item in retry_batches))
        retry_hits = [hit for hits, _ in retry_results for hit in hits]
        retry_errors = [error for _, error in retry_results if error]
        retry_count = len(retry_batches)
        logger.info(
            "Insight 豆包分组拆分重试完成: group_key={} retries={} success_parts={} failed_parts={} hits={}",
            batch.group_key,
            retry_count,
            retry_count - len(retry_errors),
            len(retry_errors),
            len(retry_hits),
        )
        deduped_hits: list[InsightSearchHit] = []
        seen_urls: set[str] = set()
        for hit in retry_hits:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            deduped_hits.append(hit)
        if not deduped_hits and retry_errors:
            raise RuntimeError(f"豆包联网搜索拆分重试失败：{retry_errors[0]['error']}")
        return deduped_hits, {"retry_count": retry_count, "retry_errors": retry_errors}

    async def _search_grouped_channel(
        self,
        batch: GroupedDiscoveryBatch,
        handler_code: str,
        *,
        freshness_override: str | None = None,
    ) -> list[InsightSearchHit]:
        count = min(30, max(12, len(batch.rows) * 4))
        freshness = freshness_override or "1d"
        if handler_code == "bocha":
            hits = await bocha_search_client.search(batch.query, count, freshness)
        elif handler_code == "doubao_web_search":
            hits = await doubao_web_search_client.search(batch.query, min(count, 15), freshness)
        else:
            hits = []
        return [
            InsightSearchHit(
                channel=hit.channel,
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                published_at=hit.published_at,
                raw=(hit.raw or {})
                | {
                    "grouped_discovery": True,
                    "group_key": batch.group_key,
                    "group_name": batch.group_name,
                    "group_query": batch.query,
                },
            )
            for hit in hits
        ]

    def _build_grouped_discovery_batches(
        self,
        rows: list[InsightMonitorConfig],
        *,
        batch_size: int | None = None,
    ) -> list[GroupedDiscoveryBatch]:
        grouped: dict[str, list[InsightMonitorConfig]] = defaultdict(list)
        for row in rows:
            if self._is_placeholder_monitor(row):
                continue
            grouped[self._group_key(row)].append(row)

        batches: list[GroupedDiscoveryBatch] = []
        resolved_batch_size = max(
            1,
            batch_size
            if batch_size is not None
            else settings.INSIGHT_SCHEDULER_GROUPED_BATCH_SIZE,
        )
        for group_key, group_rows in sorted(grouped.items(), key=lambda item: item[0]):
            ordered_rows = sorted(group_rows, key=lambda item: (item.monitor_strength != "deep", item.id or 0))
            for index in range(0, len(ordered_rows), resolved_batch_size):
                chunk = ordered_rows[index : index + resolved_batch_size]
                query = self._build_group_query(chunk)
                if not query:
                    continue
                batches.append(
                    GroupedDiscoveryBatch(
                        group_key=f"{group_key}:{index // resolved_batch_size + 1}",
                        group_name=self._group_name(chunk),
                        rows=chunk,
                        query=query,
                    )
                )
                if len(batches) >= max(1, settings.INSIGHT_SCHEDULER_GROUPED_BATCH_LIMIT):
                    return batches
        return batches

    def _is_placeholder_monitor(self, row: InsightMonitorConfig) -> bool:
        name = str(row.object_name or row.config_name or "").strip()
        if not name:
            return True
        keywords = [str(item).strip() for item in row.keywords or [] if str(item).strip()]
        if keywords:
            return False
        modules = {str(item).strip() for item in row.enabled_modules or [] if str(item).strip()}
        generic_names = set(self.scenario_modules) | {"综合", "全部", "默认"}
        return name in generic_names and (not modules or name in modules)

    def _group_key(self, row: InsightMonitorConfig) -> str:
        monitor_type = str(row.monitor_type or row.object_type or "topic").lower()
        relation = str(row.relation_type or "default").strip().lower()
        modules = [str(item).strip() for item in row.enabled_modules or [] if str(item).strip()]
        primary_module = modules[0] if modules else "综合"
        is_company_monitor = row.object_type == "company" or monitor_type in {"company", "enterprise", "企业监测"}
        prefix = "company" if is_company_monitor else "topic"
        return f"{prefix}:{relation}:{primary_module}"

    def _group_name(self, rows: list[InsightMonitorConfig]) -> str:
        names = [row.object_name or row.config_name for row in rows[:3]]
        suffix = "等" if len(rows) > 3 else ""
        return "、".join(names) + suffix

    def _build_group_query(self, rows: list[InsightMonitorConfig]) -> str:
        object_names: list[str] = []
        keywords: list[str] = []
        modules: list[str] = []
        for row in rows:
            object_name = str(row.object_name or row.config_name or "").strip()
            if object_name:
                object_names.append(object_name)
            keywords.extend(str(item).strip() for item in row.keywords or [] if str(item).strip())
            modules.extend(str(item).strip() for item in row.enabled_modules or [] if str(item).strip())
        default_terms = [
            "新品",
            "扩产",
            "供应链",
            "价格",
            "政策",
            "专利",
            "低糖",
            "配料",
            "植物蛋白",
            "功能糖",
        ]
        object_part = " OR ".join(self._unique_items(object_names)[:8])
        topic_part = " ".join(self._unique_items([*keywords, *modules, *default_terms])[:12])
        if object_part:
            return f"({object_part}) {topic_part}"[:500]
        return topic_part[:500]

    def _assign_grouped_hits(
        self,
        rows: list[InsightMonitorConfig],
        hits: list[InsightSearchHit],
    ) -> dict[int, tuple[InsightMonitorConfig, list[InsightSearchHit]]]:
        assigned: dict[int, tuple[InsightMonitorConfig, list[InsightSearchHit]]] = {}
        topic_rows = [row for row in rows if row.object_type != "company"]
        for hit in hits:
            text = f"{hit.title}\n{hit.snippet or ''}\n{hit.url}".lower()
            matched_rows: list[InsightMonitorConfig] = []
            for row in rows:
                terms = self._monitor_match_terms(row)
                if terms and any(term.lower() in text for term in terms):
                    matched_rows.append(row)
            if not matched_rows and topic_rows:
                matched_rows = topic_rows[:3]
            for row in matched_rows[:4]:
                if not row.id:
                    continue
                if row.id not in assigned:
                    assigned[row.id] = (row, [])
                assigned[row.id][1].append(hit)
        return assigned

    def _monitor_match_terms(self, row: InsightMonitorConfig) -> list[str]:
        terms = [
            str(row.object_name or "").strip(),
            str(row.config_name or "").strip(),
            *(str(item).strip() for item in row.keywords or []),
        ]
        if row.object_type != "company":
            terms.extend(str(item).strip() for item in row.enabled_modules or [])
        return [item for item in self._unique_items(terms) if len(item) >= 2][:12]

    def _unique_items(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    async def _execute_plan_items_concurrently(
        self,
        *,
        row_id: int,
        items: list[MonitorChannelPlanItem],
        query: str,
        user_id: int | None,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> list[tuple[MonitorChannelPlanItem, Any | None, Exception | None]]:
        if not items:
            return []
        api_semaphore = asyncio.Semaphore(self.api_concurrency)
        playwright_semaphore = asyncio.Semaphore(self.playwright_concurrency)
        channel_locks = {item.channel.channel_code: asyncio.Lock() for item in items}

        async def run_one(item: MonitorChannelPlanItem) -> tuple[MonitorChannelPlanItem, Any | None, Exception | None]:
            bucket = self._execution_bucket(item.channel)
            semaphore = api_semaphore if bucket == "api" else playwright_semaphore
            async with semaphore:
                async with channel_locks[item.channel.channel_code]:
                    try:
                        result = await asyncio.wait_for(
                            self._execute_search_channel_in_new_session(
                                row_id=row_id,
                                channel_id=item.channel.id or 0,
                                query=query,
                                handler_code=item.handler_code or "",
                                max_results=item.max_results,
                                user_id=user_id,
                                freshness_override=freshness_override,
                                published_start=published_start,
                                published_end=published_end,
                            ),
                            timeout=self.channel_timeout_seconds,
                        )
                        return item, result, None
                    except Exception as exc:
                        return item, None, exc

        return [await task for task in asyncio.as_completed([asyncio.create_task(run_one(item)) for item in items])]

    async def _execute_search_channel_in_new_session(
        self,
        *,
        row_id: int,
        channel_id: int,
        query: str,
        handler_code: str,
        max_results: int,
        user_id: int | None,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ) -> Any:
        async with async_session() as db:
            row = await db.get(InsightMonitorConfig, row_id)
            channel = await db.get(InsightChannel, channel_id)
            if not row or not channel:
                raise ValueError("监测配置或渠道不存在，无法执行采集")
            return await self._execute_search_channel(
                db,
                row,
                channel,
                query=query,
                handler_code=handler_code,
                max_results=max_results,
                user_id=user_id,
                freshness_override=freshness_override,
                published_start=published_start,
                published_end=published_end,
            )

    def _execution_bucket(self, channel: InsightChannel) -> str:
        if channel.channel_code in self.supported_search_channel_codes:
            return "api"
        definition = insight_channel_adapter_service.definition_for(channel.channel_code)
        if definition and definition.adapter_kind == "http":
            return "api"
        return "playwright"

    async def _active_channels(self, db: AsyncSession) -> list[InsightChannel]:
        return list(
            (
                await db.exec(
                    select(InsightChannel).where(
                        InsightChannel.is_deleted == 0,
                        InsightChannel.status == "active",
                    )
                )
            ).all()
        )

    async def _execute_search_channel(
        self,
        db: AsyncSession,
        row: InsightMonitorConfig,
        channel: InsightChannel,
        *,
        query: str,
        handler_code: str,
        max_results: int,
        user_id: int | None,
        freshness_override: str | None = None,
        published_start: datetime | None = None,
        published_end: datetime | None = None,
    ):
        request = InsightSearchDiscoveryRequest(
            query=query,
            channels=[handler_code],
            freshness=freshness_override or self._freshness_for_frequency(row.fetch_frequency),
            published_start=published_start,
            published_end=published_end,
            max_results=max_results,
            crawl_top_n=0,
            enrich_fulltext_before_review=settings.INSIGHT_REVIEW_FULLTEXT_REQUIRED,
            fulltext_top_n=max(settings.INSIGHT_REVIEW_FULLTEXT_TOP_N, 0),
            monitor_config_id=row.id,
            source_channel_id=channel.id,
            include_keywords=[],
            exclude_keywords=row.excluded_keywords or [],
            filter_prompt=self._filter_prompt(row, channel),
            enable_llm_filter=True,
            llm_min_score=0.45,
            create_candidate_from_hits=True,
            run_type=self._run_type(row),
        )
        return await insight_search_discovery_service.search_and_crawl(
            db,
            request,
            user_id=user_id,
            is_admin=True,
        )

    def _handler_for_channel(self, channel: InsightChannel) -> str | None:
        if channel.channel_code in self.supported_search_channel_codes:
            return self.supported_search_channel_codes[channel.channel_code]
        if channel.channel_code in insight_channel_adapter_service.supported_channel_codes():
            return channel.channel_code
        return None

    def _run_type(self, row: InsightMonitorConfig) -> str:
        frequency = (row.fetch_frequency or "daily").strip().lower()
        if frequency in {"weekly"}:
            return "weekly"
        if frequency in {"monthly"}:
            return "monthly"
        if frequency in {"half_month", "halfmonth", "biweekly"}:
            return "backfill"
        return "daily"

    def _build_collection_plan(
        self,
        row: InsightMonitorConfig,
        channels: list[InsightChannel],
        query: str,
        *,
        include_discovery_channels: bool = True,
        include_daily_sweep_channels: bool = True,
    ) -> MonitorCollectionPlan:
        selected_ids = {int(item) for item in row.source_channel_ids or [] if str(item).isdigit()}
        channel_by_code = {item.channel_code: item for item in channels}
        planned_codes: set[str] = set()
        items: list[MonitorChannelPlanItem] = []

        def add_channel(channel: InsightChannel, *, force: bool = False) -> None:
            if channel.channel_code in planned_codes:
                return
            if not force and not self._channel_matches_monitor(row, channel, selected_ids):
                return
            planned_codes.add(channel.channel_code)
            items.append(self._plan_channel(row, channel))

        if include_discovery_channels:
            for channel_code in self.default_search_channel_order:
                channel = channel_by_code.get(channel_code)
                if channel:
                    add_channel(channel, force=True)

        for channel in sorted(channels, key=lambda item: (item.sort_no, item.channel_name)):
            if not include_discovery_channels and channel.channel_code in self.default_search_channel_order:
                continue
            if (
                not include_daily_sweep_channels
                and channel.channel_code in self._daily_adapter_channel_codes()
            ):
                continue
            add_channel(channel)

        budget = self._collection_budget(row)
        return MonitorCollectionPlan(query=query, items=self._apply_channel_budget(row, items, budget), budget=budget)

    def _plan_channel(self, row: InsightMonitorConfig, channel: InsightChannel) -> MonitorChannelPlanItem:
        tier = self._channel_tier(channel)
        cost_level = self._channel_cost_level(channel)
        trigger_mode = self._channel_trigger_mode(channel)
        handler_code = self._handler_for_channel(channel)
        max_results = self._max_results(row, channel)
        if not self._frequency_allows_channel(row, channel):
            action = "skip"
            reason = f"该渠道默认 {channel.default_frequency or 'manual'} 采集，未到本轮频率"
        elif not handler_code:
            action = "defer"
            reason = "渠道已纳入渠道库，暂无独立适配器或脚本，本轮不执行"
        elif channel.channel_code in self.free_discovery_channel_codes:
            action = "execute"
            reason = "低成本发现源，先合并关键词执行"
        elif channel.channel_code in self.paid_discovery_channel_codes:
            action = "conditional"
            reason = "付费补充源，默认按监测对象合并关键词执行并受预算控制"
        elif channel.channel_code in self.ai_discovery_channel_codes:
            action = "conditional"
            reason = "AI 联网补充源，仅在基础发现不足、主题/深度监测或前置渠道失败时调用"
        else:
            action = "execute"
            reason = "独立适配器源，按频率和预算执行"
        return MonitorChannelPlanItem(
            channel=channel,
            action=action,
            reason=reason,
            tier=tier,
            cost_level=cost_level,
            trigger_mode=trigger_mode,
            handler_code=handler_code,
            max_results=max_results,
        )

    def _channel_matches_monitor(
        self,
        row: InsightMonitorConfig,
        channel: InsightChannel,
        selected_ids: set[int],
    ) -> bool:
        if channel.id and channel.id in selected_ids:
            return True
        if channel.channel_code in self.default_search_channel_order:
            return True
        scenarios = {str(item).strip() for item in channel.applicable_scenarios or [] if str(item).strip()}
        modules = {str(item).strip() for item in row.enabled_modules or [] if str(item).strip()}
        collection_mode = self._channel_collection_mode(channel)
        is_company_monitor = row.object_type == "company" or row.monitor_type in {"company", "enterprise", "企业监测"}
        if collection_mode in {"feed_latest", "site_search", "topic_scan"} and is_company_monitor:
            return False
        if collection_mode in {"entity_lookup", "official_watch"} and not is_company_monitor:
            return False
        if scenarios and modules and scenarios.intersection(modules):
            return True
        if is_company_monitor and scenarios.intersection({"企业新闻", "官网动态", "经营财经", "专利技术", "电商新品"}):
            return True
        if not is_company_monitor and scenarios.intersection({"行业资讯", "政策监管", "技术专利", "综合舆情"}):
            return True
        return False

    def _channel_policy(self, channel: InsightChannel) -> dict[str, Any]:
        config = channel.config_json or {}
        policy = config.get("execution_policy") if isinstance(config, dict) else None
        return policy if isinstance(policy, dict) else {}

    def _channel_tier(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        tier = str(policy.get("tier") or "").strip()
        if tier:
            return tier
        if channel.channel_code in self.default_search_channel_order:
            return "discovery"
        if channel.channel_type in {"industry_media", "finance_news", "general_news", "policy_regulation"}:
            return "vertical"
        if channel.channel_type in {"patent_technology", "database", "enterprise_official"}:
            return "specialized"
        return "custom"

    def _channel_collection_mode(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        mode = str(policy.get("collection_mode") or "").strip()
        if mode:
            return mode
        if channel.channel_code in self.default_search_channel_order:
            return "search_discovery"
        if channel.channel_type == "enterprise_official":
            return "official_watch"
        if channel.channel_type in {"patent_technology", "database"}:
            return "entity_lookup"
        if channel.channel_type in {"industry_media", "finance_news", "general_news", "policy_regulation"}:
            return "feed_latest"
        return "site_search"

    def _channel_cost_level(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        cost_level = str(policy.get("cost_level") or "").strip()
        if cost_level:
            return cost_level
        if channel.channel_code in self.paid_discovery_channel_codes:
            return "paid"
        if channel.channel_code in self.ai_discovery_channel_codes:
            return "ai_paid"
        if channel.channel_code in self.free_discovery_channel_codes:
            return "low"
        return "medium"

    def _channel_trigger_mode(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        trigger_mode = str(policy.get("trigger_mode") or "").strip()
        if trigger_mode:
            return trigger_mode
        if channel.channel_code in self.paid_discovery_channel_codes:
            return "always_with_budget"
        if channel.channel_code in self.ai_discovery_channel_codes:
            return "always_with_ai_budget"
        if channel.channel_code in self.free_discovery_channel_codes:
            return "always"
        collection_mode = self._channel_collection_mode(channel)
        if collection_mode in {"feed_latest", "topic_scan"}:
            return collection_mode
        if self._channel_tier(channel) == "vertical":
            return "channel_schedule"
        return "low_frequency"

    def _frequency_allows_channel(self, row: InsightMonitorConfig, channel: InsightChannel) -> bool:
        if channel.channel_code in self.default_search_channel_order:
            return True
        frequency = (row.fetch_frequency or "daily").strip().lower()
        channel_frequency = (channel.default_frequency or "manual").strip().lower()
        if channel_frequency == "manual":
            return False
        if frequency in {"daily", "cron", "hourly", "15m"}:
            shard = int(channel.id or sum(ord(char) for char in channel.channel_code))
            if channel_frequency == "weekly":
                return shard % 7 == datetime.now().weekday()
            if channel_frequency == "monthly":
                return shard % 28 == (datetime.now().day - 1) % 28
        return True

    def _collection_budget(self, row: InsightMonitorConfig) -> dict[str, Any]:
        config = row.config_json or {}
        raw_budget = config.get("collection_budget") if isinstance(config, dict) else None
        budget = raw_budget if isinstance(raw_budget, dict) else {}
        paid_search_calls = budget.get("paid_search_calls_per_run")
        if paid_search_calls is None:
            paid_search_calls = 1
        ai_search_calls = budget.get("ai_search_calls_per_run")
        if ai_search_calls is None:
            ai_search_calls = 1
        max_executed_channels = budget.get("max_executed_channels_per_run")
        if max_executed_channels is None:
            frequency = (row.fetch_frequency or "daily").strip().lower()
            if frequency in {"monthly"}:
                max_executed_channels = 18
            elif frequency in {"weekly", "half_month", "halfmonth", "biweekly"}:
                max_executed_channels = 12
            elif row.monitor_strength in {"deep", "structured"}:
                max_executed_channels = 8
            else:
                max_executed_channels = 6
        return {
            "paid_search_calls_per_run": max(0, int(paid_search_calls)),
            "ai_search_calls_per_run": max(0, int(ai_search_calls)),
            "max_executed_channels_per_run": max(1, int(max_executed_channels)),
            "strategy": "百度资讯先跑；博查按监测对象合并关键词默认补充 1 次；豆包联网搜索只在基础发现不足、主题/深度监测或前置渠道失败时补充；垂直渠道按自身频率和适配器状态执行",
        }

    def _apply_channel_budget(
        self,
        row: InsightMonitorConfig,
        items: list[MonitorChannelPlanItem],
        budget: dict[str, Any],
    ) -> list[MonitorChannelPlanItem]:
        max_executed_channels = int(budget.get("max_executed_channels_per_run") or 1)
        executable = [item for item in items if item.action == "execute"]
        discovery = [item for item in executable if item.channel.channel_code in self.default_search_channel_order]
        vertical = [item for item in executable if item.channel.channel_code not in self.default_search_channel_order]
        if vertical:
            offset = (datetime.now().date().toordinal() + int(row.id or 0)) % len(vertical)
            vertical = vertical[offset:] + vertical[:offset]
        execution_order = {id(item): index for index, item in enumerate([*discovery, *vertical])}
        executed_count = 0
        result: list[MonitorChannelPlanItem] = []
        for item in sorted(items, key=lambda value: execution_order.get(id(value), len(items))):
            if item.action != "execute":
                result.append(item)
                continue
            if executed_count >= max_executed_channels:
                result.append(replace(item, action="skip", reason="本轮执行渠道预算已满，延后到后续调度"))
                continue
            executed_count += 1
            result.append(item)
        return result

    def _should_run_paid_discovery(
        self,
        row: InsightMonitorConfig,
        search_results: list[Any],
        channel_errors: list[dict[str, Any]],
    ) -> bool:
        _ = row, search_results, channel_errors
        return True

    def _should_run_ai_discovery(
        self,
        row: InsightMonitorConfig,
        search_results: list[Any],
        channel_errors: list[dict[str, Any]],
    ) -> bool:
        config = row.config_json or {}
        budget = config.get("collection_budget") if isinstance(config, dict) else None
        if isinstance(budget, dict) and budget.get("force_ai_search"):
            return True
        if channel_errors:
            return True
        monitor_type = str(row.monitor_type or row.object_type or "").lower()
        is_company_monitor = row.object_type == "company" or monitor_type in {"company", "enterprise", "企业监测"}
        if not is_company_monitor:
            return True
        if row.monitor_strength in {"deep", "structured"}:
            return True
        hit_count = sum(len(getattr(item, "hits", []) or []) for item in search_results)
        candidate_count = sum(len(getattr(item, "candidates", []) or []) for item in search_results)
        return hit_count < 3 or candidate_count < 1

    async def _build_query(self, db: AsyncSession, row: InsightMonitorConfig) -> str:
        company = None
        if row.object_type == "company" and row.object_id:
            company = await db.get(InsightCompany, row.object_id)
        return self._build_query_parts(row, company)

    def _build_query_parts(self, row: InsightMonitorConfig, company: InsightCompany | None) -> str:
        parts: list[str] = []
        if row.object_name:
            parts.append(row.object_name)
        if company:
            parts.extend([company.name, company.short_name or ""])
            profile = company.profile_json or {}
            aliases = profile.get("aliases") if isinstance(profile, dict) else None
            if isinstance(aliases, list):
                parts.extend(str(item) for item in aliases[:3])
        parts.extend(row.keywords or [])
        modules = row.enabled_modules or []
        parts.extend(modules[:5])
        clean_parts = []
        seen = set()
        for part in parts:
            text = str(part or "").strip()
            if text and text not in seen:
                clean_parts.append(text)
                seen.add(text)
        if not clean_parts:
            clean_parts = [row.config_name]
        return " ".join(clean_parts)[:500]

    def _filter_prompt(self, row: InsightMonitorConfig, channel: InsightChannel) -> str:
        modules = "、".join(row.enabled_modules or [])
        relation = row.relation_type or "未指定"
        custom_prompt = (row.ai_review_prompt or "").strip()
        base = (
            f"当前监测对象：{row.object_name or row.config_name}；关系类型：{relation}；监测模块：{modules or '综合'}。"
            f"当前渠道源：{channel.channel_name}。"
            "只保留与研发营销、食品饮料、功能糖、淀粉糖、植物蛋白、配料原料、客户/竞对动态、政策法规、专利技术、渠道和新品相关的信息；"
            "过滤验证码、图片搜索、百科泛信息、无业务价值转载和明显跨行业噪声。"
        )
        if custom_prompt:
            base += f" 用户自定义 AI 口径：{custom_prompt}"
        return base[:2000]

    def _max_results(self, row: InsightMonitorConfig, channel: InsightChannel) -> int:
        if channel.channel_code == "bocha_search":
            return self._frequency_max_results(row.fetch_frequency)
        return self._frequency_max_results(row.fetch_frequency)

    def _frequency_max_results(self, fetch_frequency: str | None) -> int:
        frequency = (fetch_frequency or "daily").strip().lower()
        if frequency in {"daily", "cron", "15m", "hourly"}:
            return 10
        if frequency == "weekly":
            return 30
        return 50

    def _freshness_for_frequency(self, fetch_frequency: str | None) -> str:
        frequency = (fetch_frequency or "daily").strip().lower()
        if frequency in {"daily", "cron", "15m", "hourly"}:
            return "1d"
        if frequency == "weekly":
            return "7d"
        if frequency in {"half_month", "halfmonth", "biweekly"}:
            return "15d"
        if frequency == "monthly":
            return "30d"
        return "15d"

    def _timeout_seconds(self, row: InsightMonitorConfig) -> int:
        return 90 if row.monitor_strength in {"deep", "structured"} else 60

    def _calculate_next_run_time(
        self,
        fetch_frequency: str | None,
        config: dict | None,
        base_time: datetime,
    ) -> datetime | None:
        frequency = fetch_frequency or "manual"
        if frequency == "manual":
            return None
        if frequency == "weekly":
            return base_time + timedelta(days=7)
        if frequency in {"half_month", "halfmonth", "biweekly"}:
            return base_time + timedelta(days=15)
        if frequency == "monthly":
            return base_time + timedelta(days=30)
        if frequency == "cron":
            return base_time + timedelta(days=1)
        return base_time + timedelta(days=1)


insight_monitor_execution_service = InsightMonitorExecutionService()
