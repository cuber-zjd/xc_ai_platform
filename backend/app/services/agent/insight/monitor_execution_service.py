import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.db.session import async_session
from app.models.agent.insight import InsightChannel, InsightCompany, InsightMonitorConfig
from app.schemas.agent.insight.crawl import InsightSearchDiscoveryRequest
from app.schemas.agent.insight.data_source import InsightDataSourceScheduleExecution, InsightDataSourceScheduleRunResponse
from app.services.agent.insight.crawler.channel_adapter_service import insight_channel_adapter_service
from app.services.agent.insight.crawler import insight_search_discovery_service


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


class InsightMonitorExecutionService:
    """按监测配置执行采集，不再把旧数据源作为调度主表。"""

    supported_search_channel_codes = {"baidu_news": "baidu_news", "bocha_search": "bocha"}
    default_search_channel_order = ("baidu_news", "bocha_search")
    free_discovery_channel_codes = {"baidu_news"}
    paid_discovery_channel_codes = {"bocha_search"}
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
    api_concurrency = 8
    playwright_concurrency = 4
    channel_timeout_seconds = 180

    async def run_due_monitor_configs(
        self,
        db: AsyncSession,
        *,
        limit: int = 5,
        user_id: int | None = None,
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
        rows = list(
            (
                await db.exec(
                    select(InsightMonitorConfig)
                    .where(*due_filters)
                    .order_by(InsightMonitorConfig.next_run_time.asc().nullsfirst(), InsightMonitorConfig.id.asc())
                    .limit(limit)
                )
            ).all()
        )

        executions: list[InsightDataSourceScheduleExecution] = []
        for row in rows:
            row.last_schedule_status = "running"
            row.last_schedule_message = "监测配置采集中"
            row.last_fetch_time = datetime.now()
            row.update_time = datetime.now()
            await db.commit()
            try:
                result = await asyncio.wait_for(
                    self.execute_monitor_config(db, row, user_id=user_id),
                    timeout=self._timeout_seconds(row),
                )
                found_count = sum(len(item.hits) for item in result.get("search_results", []))
                candidate_count = sum(len(item.candidates) for item in result.get("search_results", []))
                executed_channel_count = int(result.get("executed_channel_count") or 0)
                skipped_channel_count = int(result.get("skipped_channel_count") or 0)
                planned_channel_count = int(result.get("planned_channel_count") or 0)
                paid_channel_call_count = int(result.get("paid_channel_call_count") or 0)
                plan_summary = result.get("collection_plan")
                row.last_schedule_status = "success"
                row.last_schedule_message = (
                    f"计划 {planned_channel_count} 个渠道，执行 {executed_channel_count} 个，"
                    f"付费补充 {paid_channel_call_count} 次，跳过/暂缓 {skipped_channel_count} 个；"
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
    ) -> dict[str, Any]:
        channels = await self._active_channels(db)
        query = await self._build_query(db, row)
        plan = self._build_collection_plan(row, channels, query)
        if not plan.items:
            raise ValueError("当前监测配置没有匹配到可用渠道源")

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

        should_run_paid_search = self._should_run_paid_discovery(row, search_results, channel_errors)
        paid_budget = int(plan.budget.get("paid_search_calls_per_run") or 0)
        conditional_to_run: list[MonitorChannelPlanItem] = []
        for item in plan.conditional_items():
            if item.channel.channel_code in self.paid_discovery_channel_codes and not should_run_paid_search:
                skipped_channels.append(item.to_dict() | {"reason": "百度资讯结果已满足本轮入库需要，未调用付费补充源"})
                continue
            if item.channel.channel_code in self.paid_discovery_channel_codes and paid_channel_call_count >= paid_budget:
                skipped_channels.append(item.to_dict() | {"reason": "本轮付费搜索预算已用完"})
                continue
            conditional_to_run.append(item)
            if item.channel.channel_code in self.paid_discovery_channel_codes:
                paid_channel_call_count += 1

        conditional_results = await self._execute_plan_items_concurrently(
            row_id=row.id or 0,
            items=conditional_to_run,
            query=query,
            user_id=user_id,
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
            "executed_channels": executed_channels,
            "skipped_channels": skipped_channels[:50],
            "channel_errors": channel_errors[:20],
        }

    async def _execute_plan_items_concurrently(
        self,
        *,
        row_id: int,
        items: list[MonitorChannelPlanItem],
        query: str,
        user_id: int | None,
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
    ):
        request = InsightSearchDiscoveryRequest(
            query=query,
            channels=[handler_code],
            freshness="halfMonth",
            max_results=max_results,
            crawl_top_n=0,
            monitor_config_id=row.id,
            source_channel_id=channel.id,
            include_keywords=[],
            exclude_keywords=row.excluded_keywords or [],
            filter_prompt=self._filter_prompt(row, channel),
            enable_llm_filter=True,
            llm_min_score=0.55,
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

        for channel_code in self.default_search_channel_order:
            channel = channel_by_code.get(channel_code)
            if channel:
                add_channel(channel, force=True)

        for channel in sorted(channels, key=lambda item: (item.sort_no, item.channel_name)):
            add_channel(channel)

        budget = self._collection_budget(row)
        return MonitorCollectionPlan(query=query, items=self._apply_channel_budget(items, budget), budget=budget)

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
            reason = "付费补充源，仅在低成本发现不足或质量不足时调用"
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
        if scenarios and modules and scenarios.intersection(modules):
            return True
        is_company_monitor = row.object_type == "company" or row.monitor_type in {"company", "enterprise", "企业监测"}
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

    def _channel_cost_level(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        cost_level = str(policy.get("cost_level") or "").strip()
        if cost_level:
            return cost_level
        if channel.channel_code in self.paid_discovery_channel_codes:
            return "paid"
        if channel.channel_code in self.free_discovery_channel_codes:
            return "low"
        return "medium"

    def _channel_trigger_mode(self, channel: InsightChannel) -> str:
        policy = self._channel_policy(channel)
        trigger_mode = str(policy.get("trigger_mode") or "").strip()
        if trigger_mode:
            return trigger_mode
        if channel.channel_code in self.paid_discovery_channel_codes:
            return "quality_gap"
        if channel.channel_code in self.free_discovery_channel_codes:
            return "always"
        if self._channel_tier(channel) == "vertical":
            return "channel_schedule"
        return "low_frequency"

    def _frequency_allows_channel(self, row: InsightMonitorConfig, channel: InsightChannel) -> bool:
        if channel.channel_code in self.default_search_channel_order:
            return True
        frequency = (row.fetch_frequency or "daily").strip().lower()
        channel_frequency = (channel.default_frequency or "manual").strip().lower()
        if channel_frequency in {"manual", "monthly"} and frequency in {"daily", "cron", "hourly", "15m"}:
            return False
        if channel_frequency == "weekly" and frequency in {"daily", "cron", "hourly", "15m"}:
            return False
        return True

    def _collection_budget(self, row: InsightMonitorConfig) -> dict[str, Any]:
        config = row.config_json or {}
        raw_budget = config.get("collection_budget") if isinstance(config, dict) else None
        budget = raw_budget if isinstance(raw_budget, dict) else {}
        paid_search_calls = budget.get("paid_search_calls_per_run")
        if paid_search_calls is None:
            paid_search_calls = 1 if row.monitor_strength in {"standard", "deep", "structured"} else 0
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
            "max_executed_channels_per_run": max(1, int(max_executed_channels)),
            "strategy": "百度资讯优先；结果不足或质量不足时再调用博查；垂直渠道按自身频率和适配器状态执行",
        }

    def _apply_channel_budget(
        self,
        items: list[MonitorChannelPlanItem],
        budget: dict[str, Any],
    ) -> list[MonitorChannelPlanItem]:
        max_executed_channels = int(budget.get("max_executed_channels_per_run") or 1)
        executed_count = 0
        result: list[MonitorChannelPlanItem] = []
        for item in items:
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
        if not search_results:
            return True
        hit_count = sum(len(item.hits) for item in search_results)
        candidate_count = sum(len(item.candidates) for item in search_results)
        if channel_errors and hit_count < 3:
            return True
        if row.monitor_strength in {"deep", "structured"}:
            return hit_count < 8 or candidate_count < 3
        return hit_count < 5 or candidate_count < 2

    async def _build_query(self, db: AsyncSession, row: InsightMonitorConfig) -> str:
        parts: list[str] = []
        if row.object_name:
            parts.append(row.object_name)
        if row.object_type == "company" and row.object_id:
            company = await db.get(InsightCompany, row.object_id)
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
