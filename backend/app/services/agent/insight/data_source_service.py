import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, exists, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight import InsightChannel, InsightCompany, InsightDataSource, InsightMonitorConfig, InsightTask, InsightTaskStatus
from app.schemas.agent.insight.crawl import InsightManualUrlCrawlRequest, InsightSearchDiscoveryRequest
from app.schemas.agent.insight.data_source import (
    InsightDataSourceBatchCreateItem,
    InsightDataSourceBatchCreateRequest,
    InsightDataSourceBatchCreateResponse,
    InsightDataSourceBulkActionRequest,
    InsightDataSourceBulkActionResponse,
    InsightDataSourceCreate,
    InsightDataSourceExecuteRequest,
    InsightDataSourceExecuteResponse,
    InsightDataSourceFetchConfig,
    InsightDataSourceGroupRead,
    InsightDataSourceRead,
    InsightDataSourceScheduleExecution,
    InsightDataSourceScheduleRunResponse,
    InsightDataSourceUpdate,
    InsightStaleTaskCleanupResponse,
)
from app.schemas.agent.insight.monitor_config import InsightLegacySourceSyncResponse
from app.schemas.agent.insight.task import InsightTaskRead
from app.schemas.page import Page
from app.services.agent.insight.crawler import insight_crawl_service, insight_search_discovery_service
from app.services.agent.insight.permission_service import insight_permission_service


class InsightDataSourceService:
    allowed_source_types = {
        "baidu_news",
        "baidu_search",
        "bocha_search",
        "bocha_news",
        "bocha_web",
        "multi_news",
        "official_site",
        "web_page",
        "wechat_public_account",
        "ecommerce_search",
        "government_policy",
        "finance_news",
        "patent_search",
        "industry_media",
    }
    web_source_types = {"official_site", "web_page"}
    allowed_fetch_frequencies = {"manual", "15m", "hourly", "daily", "weekly", "cron"}
    allowed_statuses = {"enabled", "disabled"}
    allowed_visibility_scopes = {"private", "assigned", "dept", "role", "public"}
    allowed_auto_review_modes = {"off", "high_confidence", "all"}
    allowed_generation_modes = {"manual", "system_generated", "user_created", "legacy_migrated", "imported"}
    allowed_collection_strategies = {"light", "standard", "deep", "structured"}

    async def run_due_data_sources(
        self,
        db: AsyncSession,
        *,
        limit: int = 5,
        user_id: int | None = None,
    ) -> InsightDataSourceScheduleRunResponse:
        limit = min(max(limit, 1), 20)
        now = datetime.now()
        filters = [
            InsightDataSource.is_deleted == 0,
            InsightDataSource.status == "enabled",
            InsightDataSource.schedule_enabled == True,  # noqa: E712
            InsightDataSource.fetch_frequency != "manual",
            or_(InsightDataSource.next_run_time == None, InsightDataSource.next_run_time <= now),  # noqa: E711
        ]
        checked_count = (
            await db.exec(
                select(func.count())
                .select_from(InsightDataSource)
                .where(
                    InsightDataSource.is_deleted == 0,
                    InsightDataSource.status == "enabled",
                    InsightDataSource.schedule_enabled == True,  # noqa: E712
                    InsightDataSource.fetch_frequency != "manual",
                )
            )
        ).one()
        due_count = (await db.exec(select(func.count()).select_from(InsightDataSource).where(*filters))).one()
        rows = list(
            (
                await db.exec(
                    select(InsightDataSource)
                    .where(*filters)
                    .order_by(InsightDataSource.next_run_time.asc().nullsfirst(), InsightDataSource.id.asc())
                    .limit(limit)
                )
            ).all()
        )
        executions: list[InsightDataSourceScheduleExecution] = []
        for row in rows:
            row.last_schedule_status = "running"
            row.last_schedule_message = "周期采集执行中"
            row.update_time = datetime.now()
            await db.commit()
            try:
                result = await asyncio.wait_for(
                    self.execute_data_source(
                        db,
                        row.id or 0,
                        InsightDataSourceExecuteRequest(),
                        user_id,
                        is_admin=True,
                    ),
                    timeout=self._schedule_source_timeout_seconds(row.fetch_config),
                )
                search_results = result.search_results or ([result.search_result] if result.search_result else [])
                found_count = sum(len(item.hits) for item in search_results) or (1 if result.manual_result else 0)
                candidate_count = sum(len(item.candidates) for item in search_results) or (1 if result.manual_result else 0)
                row = await self._get_data_source(db, row.id or 0)
                row.last_schedule_status = "success"
                row.last_schedule_message = f"发现 {found_count} 条，候选 {candidate_count} 条"
                row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.fetch_config, datetime.now())
                row.consecutive_failure_count = 0
                row.last_failure_time = None
                row.auto_paused_reason = None
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
                await db.commit()
                executions.append(
                    InsightDataSourceScheduleExecution(
                        data_source_id=row.id or 0,
                        source_name=row.source_name,
                        status="success",
                        message=row.last_schedule_message,
                        next_run_time=row.next_run_time,
                        found_count=found_count,
                        candidate_count=candidate_count,
                    )
                )
            except Exception as exc:
                row = await self._get_data_source(db, row.id or 0)
                row.last_schedule_status = "failed"
                row.last_schedule_message = str(exc)[:1000]
                row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.fetch_config, datetime.now())
                row.consecutive_failure_count = (row.consecutive_failure_count or 0) + 1
                row.last_failure_time = datetime.now()
                if row.consecutive_failure_count >= settings.INSIGHT_SCHEDULER_FAILURE_PAUSE_THRESHOLD:
                    row.schedule_enabled = False
                    row.last_schedule_status = "paused"
                    row.auto_paused_reason = (
                        f"连续失败 {row.consecutive_failure_count} 次，已自动暂停周期采集。最近错误：{str(exc)[:700]}"
                    )[:1000]
                    row.last_schedule_message = row.auto_paused_reason
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
                await db.commit()
                executions.append(
                    InsightDataSourceScheduleExecution(
                        data_source_id=row.id or 0,
                        source_name=row.source_name,
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

    async def retry_data_source(
        self,
        db: AsyncSession,
        *,
        data_source_id: int,
        user_id: int | None = None,
        is_admin: bool = False,
    ) -> InsightDataSourceRead:
        row = await self._get_data_source(db, data_source_id, user_id=user_id, is_admin=is_admin, permission="edit")
        row.status = "enabled"
        row.schedule_enabled = self._resolve_schedule_enabled(row.fetch_frequency, True)
        row.next_run_time = datetime.now()
        row.last_schedule_status = "waiting"
        row.last_schedule_message = "已人工重试，等待下一轮调度扫描"
        row.auto_paused_reason = None
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return await self._to_read_with_company(db, row)

    async def cleanup_stale_tasks(
        self,
        db: AsyncSession,
        *,
        timeout_minutes: int = 30,
        user_id: int | None = None,
    ) -> InsightStaleTaskCleanupResponse:
        timeout_minutes = min(max(timeout_minutes, 1), 24 * 60)
        cutoff = datetime.now() - timedelta(minutes=timeout_minutes)
        statement = (
            select(InsightTask)
            .where(
                InsightTask.is_deleted == 0,
                InsightTask.status.in_([InsightTaskStatus.PENDING, InsightTaskStatus.RUNNING]),
                InsightTask.create_time <= cutoff,
            )
            .order_by(InsightTask.create_time.asc())
            .limit(500)
        )
        rows = list((await db.exec(statement)).all())
        task_ids: list[int] = []
        for row in rows:
            row.status = InsightTaskStatus.FAILED
            row.progress = 100
            row.finished_at = datetime.now()
            row.error_message = f"任务超过 {timeout_minutes} 分钟未完成，已由 P0 封版清理标记为超时"
            payload = row.output_payload or {}
            payload["cleanup"] = {
                "reason": "timeout",
                "timeout_minutes": timeout_minutes,
                "cleanup_user_id": user_id,
                "cleanup_time": datetime.now().isoformat(),
            }
            row.output_payload = payload
            row.update_time = datetime.now()
            row.update_by = str(user_id) if user_id else None
            if row.id:
                task_ids.append(row.id)
        if rows:
            await db.commit()
        return InsightStaleTaskCleanupResponse(
            timeout_minutes=timeout_minutes,
            cleaned_count=len(task_ids),
            task_ids=task_ids,
        )

    async def list_execution_logs(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        data_source_id: int | None,
        status: str | None,
        task_type: str | None = None,
    ) -> Page[InsightTaskRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        allowed_task_types = {"manual_url_crawl", "keyword_search_discovery", "scheduler_tick"}
        filters = [InsightTask.is_deleted == 0]
        if task_type:
            filters.append(InsightTask.task_type == task_type)
        else:
            filters.append(InsightTask.task_type.in_(list(allowed_task_types)))
        if data_source_id:
            filters.append(InsightTask.data_source_id == data_source_id)
        if status:
            filters.append(InsightTask.status == status)

        total = (await db.exec(select(func.count()).select_from(InsightTask).where(*filters))).one()
        statement = (
            select(InsightTask)
            .where(*filters)
            .order_by(InsightTask.started_at.desc().nullslast(), InsightTask.create_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await db.exec(statement)).all())
        return Page.create(items=[self._to_task_read(row) for row in rows], total=total, page=page, size=size)

    async def list_data_sources(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None,
        source_type: str | None,
        status: str | None,
        monitor_config_id: int | None = None,
        execution_role: str | None = None,
        channel_id: int | None = None,
        user_id: int,
        is_admin: bool,
    ) -> Page[InsightDataSourceRead]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightDataSource.is_deleted == 0]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightDataSource.source_name.ilike(like_keyword),
                    InsightDataSource.source_code.ilike(like_keyword),
                    InsightDataSource.base_url.ilike(like_keyword),
                )
            )
        if source_type:
            filters.append(InsightDataSource.source_type == source_type)
        if status:
            filters.append(InsightDataSource.status == status)
        if monitor_config_id:
            filters.append(InsightDataSource.monitor_config_id == monitor_config_id)
        if execution_role:
            filters.append(InsightDataSource.execution_role == execution_role)
        if channel_id:
            filters.append(InsightDataSource.channel_id == channel_id)
        filters.append(
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
            )
        )
        filters.append(await self._data_source_company_scope_filter(db, user_id=user_id, is_admin=is_admin))

        total = (await db.exec(select(func.count()).select_from(InsightDataSource).where(*filters))).one()
        statement = (
            select(InsightDataSource)
            .where(*filters)
            .order_by(InsightDataSource.update_time.desc(), InsightDataSource.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await db.exec(statement)).all())
        return Page.create(items=[await self._to_read_with_company(db, row) for row in rows], total=total, page=page, size=size)

    async def bulk_action(
        self,
        db: AsyncSession,
        payload: InsightDataSourceBulkActionRequest,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightDataSourceBulkActionResponse:
        action = payload.action.strip()
        allowed_actions = {"enable", "disable", "delete", "set_schedule", "set_visibility", "patch_config", "execute"}
        if action not in allowed_actions:
            raise ValueError(f"批量动作不支持：{action}")
        response = InsightDataSourceBulkActionResponse(
            action=action,
            requested_count=len(payload.data_source_ids),
        )
        for data_source_id in payload.data_source_ids:
            try:
                if action == "execute":
                    result = await self.execute_data_source(
                        db,
                        data_source_id,
                        InsightDataSourceExecuteRequest(crawl_top_n=payload.execute_crawl_top_n),
                        user_id,
                        is_admin=is_admin,
                    )
                    candidate_count = sum(len(item.candidates) for item in result.search_results)
                    response.items.append(
                        {
                            "data_source_id": data_source_id,
                            "status": "success",
                            "candidate_count": candidate_count,
                            "execution_errors": result.execution_errors,
                        }
                    )
                    response.success_count += 1
                    continue

                row = await self._get_data_source(db, data_source_id, user_id=user_id, is_admin=is_admin, permission="edit")
                if action == "enable":
                    row.status = "enabled"
                    row.schedule_enabled = self._resolve_schedule_enabled(row.fetch_frequency, row.schedule_enabled)
                elif action == "disable":
                    row.status = "disabled"
                    row.schedule_enabled = False
                    row.next_run_time = None
                elif action == "delete":
                    row.is_deleted = 1
                    row.status = "deleted"
                    row.schedule_enabled = False
                    row.next_run_time = None
                elif action == "set_schedule":
                    if payload.fetch_frequency:
                        row.fetch_frequency = payload.fetch_frequency
                    if payload.schedule_enabled is not None:
                        row.schedule_enabled = self._resolve_schedule_enabled(row.fetch_frequency, payload.schedule_enabled)
                    row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.fetch_config, datetime.now()) if row.schedule_enabled else None
                elif action == "set_visibility":
                    if not payload.visibility_scope:
                        raise ValueError("批量设置权限范围时必须提供 visibility_scope")
                    row.visibility_scope = payload.visibility_scope
                elif action == "patch_config":
                    config = self._normalize_fetch_config(row.fetch_config)
                    config.update(payload.fetch_config_patch or {})
                    row.fetch_config = self._normalize_fetch_config(config)
                    if payload.fetch_frequency:
                        row.fetch_frequency = payload.fetch_frequency
                    if payload.schedule_enabled is not None:
                        row.schedule_enabled = self._resolve_schedule_enabled(row.fetch_frequency, payload.schedule_enabled)
                    if payload.visibility_scope:
                        row.visibility_scope = payload.visibility_scope
                    row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.fetch_config, datetime.now()) if row.schedule_enabled else None
                self._validate_data_source_config(
                    source_type=row.source_type,
                    base_url=row.base_url,
                    fetch_frequency=row.fetch_frequency,
                    fetch_config=row.fetch_config,
                    schedule_enabled=row.schedule_enabled,
                    status=row.status if row.status != "deleted" else "disabled",
                    visibility_scope=row.visibility_scope,
                )
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
                await db.commit()
                response.items.append({"data_source_id": data_source_id, "status": "success"})
                response.success_count += 1
            except Exception as exc:
                await db.rollback()
                response.items.append({"data_source_id": data_source_id, "status": "failed", "message": str(exc)})
                response.failed_count += 1
        return response

    async def list_data_source_groups(
        self,
        db: AsyncSession,
        *,
        keyword: str | None,
        source_type: str | None,
        status: str | None,
        monitor_config_id: int | None = None,
        execution_role: str | None = None,
        channel_id: int | None = None,
        user_id: int,
        is_admin: bool,
    ) -> list[InsightDataSourceGroupRead]:
        filters = [InsightDataSource.is_deleted == 0]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightDataSource.source_name.ilike(like_keyword),
                    InsightDataSource.source_code.ilike(like_keyword),
                    InsightDataSource.base_url.ilike(like_keyword),
                    InsightCompany.name.ilike(like_keyword),
                    InsightCompany.short_name.ilike(like_keyword),
                )
            )
        if source_type:
            filters.append(InsightDataSource.source_type == source_type)
        if status:
            filters.append(InsightDataSource.status == status)
        if monitor_config_id:
            filters.append(InsightDataSource.monitor_config_id == monitor_config_id)
        if execution_role:
            filters.append(InsightDataSource.execution_role == execution_role)
        if channel_id:
            filters.append(InsightDataSource.channel_id == channel_id)
        filters.append(
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
            )
        )
        filters.append(await self._data_source_company_scope_filter(db, user_id=user_id, is_admin=is_admin))
        rows = list(
            (
                await db.exec(
                    select(InsightDataSource, InsightCompany, InsightMonitorConfig, InsightChannel)
                    .join(InsightCompany, InsightCompany.id == InsightDataSource.company_id, isouter=True)
                    .join(InsightMonitorConfig, InsightMonitorConfig.id == InsightDataSource.monitor_config_id, isouter=True)
                    .join(InsightChannel, InsightChannel.id == InsightDataSource.channel_id, isouter=True)
                    .where(*filters)
                    .order_by(
                        InsightMonitorConfig.config_name.asc().nullslast(),
                        InsightCompany.name.asc().nullslast(),
                        InsightDataSource.source_type.asc(),
                        InsightDataSource.update_time.desc(),
                    )
                )
            ).all()
        )
        groups: dict[tuple[int | None, str], dict] = {}
        for row, company, monitor_config, channel in rows:
            key = (row.monitor_config_id, row.company_id, row.execution_role or row.source_type, row.channel_id)
            group = groups.setdefault(
                key,
                {
                    "company": company,
                    "monitor_config": monitor_config,
                    "channel": channel,
                    "source_type": row.source_type,
                    "execution_role": row.execution_role or row.source_type,
                    "rows": [],
                },
            )
            group["rows"].append(row)

        result: list[InsightDataSourceGroupRead] = []
        for (group_monitor_config_id, company_id, group_execution_role, group_channel_id), group in groups.items():
            group_rows: list[InsightDataSource] = group["rows"]
            company = group["company"]
            monitor_config = group["monitor_config"]
            channel = group["channel"]
            visibility_scopes = sorted({row.visibility_scope for row in group_rows if row.visibility_scope})
            result.append(
                InsightDataSourceGroupRead(
                    group_key=f"{group_monitor_config_id or 'legacy'}:{company_id or 'none'}:{group_execution_role}:{group_channel_id or 'none'}",
                    monitor_config_id=group_monitor_config_id,
                    monitor_config_name=monitor_config.config_name if monitor_config else None,
                    monitor_type=monitor_config.monitor_type if monitor_config else None,
                    execution_role=group_execution_role,
                    channel_id=group_channel_id,
                    channel_name=channel.channel_name if channel else None,
                    company_id=company_id,
                    company_name=company.name if company else "未关联企业",
                    company_short_name=company.short_name if company else None,
                    sys_company_id=company.sys_company_id if company else None,
                    source_type=group["source_type"],
                    source_type_label=self._execution_role_label(group_execution_role),
                    total_count=len(group_rows),
                    enabled_count=sum(1 for row in group_rows if row.status == "enabled"),
                    disabled_count=sum(1 for row in group_rows if row.status == "disabled"),
                    scheduled_count=sum(1 for row in group_rows if row.schedule_enabled),
                    llm_filter_count=sum(1 for row in group_rows if bool((row.fetch_config or {}).get("enable_llm_filter"))),
                    auto_review_count=sum(1 for row in group_rows if str((row.fetch_config or {}).get("auto_review_mode") or "off") != "off"),
                    failed_count=sum(1 for row in group_rows if row.last_schedule_status == "failed"),
                    paused_count=sum(1 for row in group_rows if row.last_schedule_status == "paused" or bool(row.auto_paused_reason)),
                    latest_success_time=max((row.last_success_time for row in group_rows if row.last_success_time), default=None),
                    latest_failure_time=max((row.last_failure_time for row in group_rows if row.last_failure_time), default=None),
                    next_run_time=min((row.next_run_time for row in group_rows if row.next_run_time), default=None),
                    visibility_scopes=visibility_scopes,
                    data_source_ids=[row.id for row in group_rows if row.id is not None],
                )
            )
        return sorted(result, key=lambda item: (item.company_name or "", item.source_type_label))

    async def get_data_source(
        self,
        db: AsyncSession,
        data_source_id: int,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightDataSourceRead:
        return await self._to_read_with_company(
            db,
            await self._get_data_source(
                db,
                data_source_id,
                user_id=user_id,
                is_admin=is_admin,
            ),
        )

    async def create_data_source(
        self,
        db: AsyncSession,
        payload: InsightDataSourceCreate,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightDataSourceRead:
        source_code = payload.source_code or f"src_{uuid4().hex[:16]}"
        existing = (await db.exec(select(InsightDataSource).where(InsightDataSource.source_code == source_code))).first()
        if existing:
            raise ValueError("数据源编码已存在")
        config = self._normalize_fetch_config(payload.fetch_config)
        self._validate_data_source_config(
            source_type=payload.source_type,
            base_url=payload.base_url,
            fetch_frequency=payload.fetch_frequency,
            fetch_config=config,
            schedule_enabled=payload.schedule_enabled,
            status=payload.status,
            visibility_scope=payload.visibility_scope,
            generation_mode=payload.generation_mode,
            collection_strategy=payload.collection_strategy,
        )
        await self._ensure_company_access(db, payload.company_id, user_id=user_id, is_admin=is_admin)
        await self._ensure_monitor_config_exists(db, payload.monitor_config_id)
        await self._ensure_channel_exists(db, payload.channel_id)
        row = InsightDataSource(
            source_code=source_code,
            source_name=payload.source_name,
            source_type=payload.source_type,
            base_url=payload.base_url,
            channel_id=payload.channel_id,
            monitor_config_id=payload.monitor_config_id,
            monitor_object_type=payload.monitor_object_type,
            monitor_object_id=payload.monitor_object_id,
            execution_role=payload.execution_role or self._execution_role_for_source_type(payload.source_type),
            generation_mode=payload.generation_mode,
            collection_strategy=payload.collection_strategy,
            company_id=payload.company_id,
            fetch_frequency=payload.fetch_frequency,
            fetch_config=config,
            auth_config_ref=payload.auth_config_ref,
            schedule_enabled=self._resolve_schedule_enabled(payload.fetch_frequency, payload.schedule_enabled),
            next_run_time=self._calculate_next_run_time(payload.fetch_frequency, config, datetime.now())
            if self._resolve_schedule_enabled(payload.fetch_frequency, payload.schedule_enabled)
            else None,
            last_schedule_status="waiting" if self._resolve_schedule_enabled(payload.fetch_frequency, payload.schedule_enabled) else None,
            owner_user_id=user_id,
            visibility_scope=payload.visibility_scope,
            status=payload.status,
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return await self._to_read_with_company(db, row)

    async def batch_create_data_sources(
        self,
        db: AsyncSession,
        payload: InsightDataSourceBatchCreateRequest,
        *,
        user_id: int,
        is_admin: bool,
    ) -> InsightDataSourceBatchCreateResponse:
        company_ids = self._dedupe_ints(payload.company_ids)
        source_types = self._dedupe_keywords(payload.source_types)
        response = InsightDataSourceBatchCreateResponse(
            requested_company_count=len(company_ids),
            requested_type_count=len(source_types),
            requested_count=len(company_ids) * len(source_types),
        )
        companies = list(
            (
                await db.exec(
                    select(InsightCompany)
                    .where(InsightCompany.id.in_(company_ids), InsightCompany.is_deleted == 0, InsightCompany.status == "active")
                    .order_by(InsightCompany.name.asc())
                )
            ).all()
        )
        company_map = {company.id: company for company in companies if company.id is not None}
        user_sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id) if not is_admin else None

        for company_id in company_ids:
            company = company_map.get(company_id)
            if not company:
                response.items.append(
                    InsightDataSourceBatchCreateItem(
                        company_id=company_id,
                        company_name="",
                        source_type="",
                        source_name="",
                        source_code="",
                        status="failed",
                        message="企业不存在或已停用",
                    )
                )
                response.failed_count += len(source_types) or 1
                continue
            if not is_admin and company.sys_company_id != user_sys_company_id:
                response.items.append(
                    InsightDataSourceBatchCreateItem(
                        company_id=company.id or company_id,
                        company_name=company.name,
                        source_type="",
                        source_name="",
                        source_code="",
                        status="failed",
                        message="无权为其他所属公司的企业创建数据源",
                    )
                )
                response.failed_count += len(source_types) or 1
                continue
            for source_type in source_types:
                source_name = f"{company.short_name or company.name}-{self._source_type_label(source_type)}"
                source_code = self._batch_source_code(company.id or 0, source_type)
                try:
                    if source_type not in self.allowed_source_types:
                        raise ValueError(f"数据源类型不支持：{source_type}")
                    if source_type in self.web_source_types:
                        raise ValueError("官网/通用网页需要明确 URL，不能通过批量标准源自动生成")

                    config = self._build_batch_fetch_config(payload, company, source_type)
                    self._validate_data_source_config(
                        source_type=source_type,
                        base_url=None,
                        fetch_frequency=payload.fetch_frequency,
                        fetch_config=config,
                        schedule_enabled=None,
                        status=payload.status,
                        visibility_scope=payload.visibility_scope,
                    )
                    existing = (await db.exec(select(InsightDataSource).where(InsightDataSource.source_code == source_code))).first()
                    if existing and existing.is_deleted == 0 and not payload.update_existing:
                        response.items.append(
                            InsightDataSourceBatchCreateItem(
                                company_id=company.id or company_id,
                                company_name=company.name,
                                source_type=source_type,
                                source_name=existing.source_name,
                                source_code=source_code,
                                status="skipped",
                                data_source_id=existing.id,
                                message="已存在，未更新",
                            )
                        )
                        response.skipped_count += 1
                        continue

                    if existing:
                        existing.source_name = source_name
                        existing.source_type = source_type
                        existing.base_url = None
                        existing.monitor_config_id = existing.monitor_config_id or await self._ensure_company_monitor_config(
                            db,
                            company,
                            user_id=user_id,
                            generation_mode="system_generated",
                        )
                        existing.monitor_object_type = "company"
                        existing.monitor_object_id = company.id
                        existing.execution_role = self._execution_role_for_source_type(source_type)
                        existing.generation_mode = existing.generation_mode or "system_generated"
                        existing.collection_strategy = existing.collection_strategy or "standard"
                        existing.company_id = company.id
                        existing.fetch_frequency = payload.fetch_frequency
                        existing.fetch_config = config
                        existing.schedule_enabled = self._resolve_schedule_enabled(payload.fetch_frequency, None)
                        existing.next_run_time = self._calculate_next_run_time(payload.fetch_frequency, config, datetime.now()) if existing.schedule_enabled else None
                        existing.last_schedule_status = "waiting" if existing.schedule_enabled else existing.last_schedule_status
                        existing.visibility_scope = payload.visibility_scope
                        existing.status = payload.status
                        existing.is_deleted = 0
                        existing.update_by = str(user_id)
                        existing.update_time = datetime.now()
                        await db.commit()
                        await db.refresh(existing)
                        response.items.append(
                            InsightDataSourceBatchCreateItem(
                                company_id=company.id or company_id,
                                company_name=company.name,
                                source_type=source_type,
                                source_name=source_name,
                                source_code=source_code,
                                status="updated",
                                data_source_id=existing.id,
                                message="已更新标准配置",
                            )
                        )
                        response.updated_count += 1
                        continue

                    row = InsightDataSource(
                        source_code=source_code,
                        source_name=source_name,
                        source_type=source_type,
                        monitor_config_id=await self._ensure_company_monitor_config(
                            db,
                            company,
                            user_id=user_id,
                            generation_mode="system_generated",
                        ),
                        monitor_object_type="company",
                        monitor_object_id=company.id,
                        execution_role=self._execution_role_for_source_type(source_type),
                        generation_mode="system_generated",
                        collection_strategy="standard",
                        company_id=company.id,
                        fetch_frequency=payload.fetch_frequency,
                        fetch_config=config,
                        schedule_enabled=self._resolve_schedule_enabled(payload.fetch_frequency, None),
                        next_run_time=self._calculate_next_run_time(payload.fetch_frequency, config, datetime.now())
                        if self._resolve_schedule_enabled(payload.fetch_frequency, None)
                        else None,
                        last_schedule_status="waiting" if self._resolve_schedule_enabled(payload.fetch_frequency, None) else None,
                        owner_user_id=user_id,
                        visibility_scope=payload.visibility_scope,
                        status=payload.status,
                        create_by=str(user_id),
                        update_by=str(user_id),
                    )
                    db.add(row)
                    await db.commit()
                    await db.refresh(row)
                    response.items.append(
                        InsightDataSourceBatchCreateItem(
                            company_id=company.id or company_id,
                            company_name=company.name,
                            source_type=source_type,
                            source_name=source_name,
                            source_code=source_code,
                            status="created",
                            data_source_id=row.id,
                            message="已创建",
                        )
                    )
                    response.created_count += 1
                except Exception as exc:
                    await db.rollback()
                    response.items.append(
                        InsightDataSourceBatchCreateItem(
                            company_id=company.id or company_id,
                            company_name=company.name,
                            source_type=source_type,
                            source_name=source_name,
                            source_code=source_code,
                            status="failed",
                            message=str(exc),
                        )
                    )
                    response.failed_count += 1
        return response

    async def update_data_source(
        self,
        db: AsyncSession,
        data_source_id: int,
        payload: InsightDataSourceUpdate,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightDataSourceRead:
        row = await self._get_data_source(db, data_source_id, user_id=user_id, is_admin=is_admin, permission="edit")
        data = payload.model_dump(exclude_unset=True)
        if "fetch_config" in data:
            data["fetch_config"] = self._normalize_fetch_config(data["fetch_config"])
        if "company_id" in data:
            await self._ensure_company_access(db, data.get("company_id"), user_id=user_id, is_admin=is_admin)
        if "monitor_config_id" in data:
            await self._ensure_monitor_config_exists(db, data.get("monitor_config_id"))
        if "channel_id" in data:
            await self._ensure_channel_exists(db, data.get("channel_id"))
        self._validate_data_source_config(
            source_type=data.get("source_type", row.source_type),
            base_url=data.get("base_url", row.base_url),
            fetch_frequency=data.get("fetch_frequency", row.fetch_frequency),
            fetch_config=data.get("fetch_config", row.fetch_config),
            schedule_enabled=data.get("schedule_enabled", row.schedule_enabled),
            status=data.get("status", row.status),
            visibility_scope=data.get("visibility_scope", row.visibility_scope),
            generation_mode=data.get("generation_mode", row.generation_mode),
            collection_strategy=data.get("collection_strategy", row.collection_strategy),
        )
        for field, value in data.items():
            setattr(row, field, value)
        if "fetch_frequency" in data or "fetch_config" in data or "schedule_enabled" in data:
            row.schedule_enabled = self._resolve_schedule_enabled(row.fetch_frequency, row.schedule_enabled)
            row.next_run_time = self._calculate_next_run_time(row.fetch_frequency, row.fetch_config, datetime.now()) if row.schedule_enabled else None
            if row.schedule_enabled and not row.last_schedule_status:
                row.last_schedule_status = "waiting"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return await self._to_read_with_company(db, row)

    async def delete_data_source(
        self,
        db: AsyncSession,
        data_source_id: int,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> None:
        row = await self._get_data_source(db, data_source_id, user_id=user_id, is_admin=is_admin, permission="edit")
        row.is_deleted = 1
        row.status = "deleted"
        row.update_by = str(user_id) if user_id else None
        row.update_time = datetime.now()
        await db.commit()

    async def sync_legacy_sources(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
    ) -> InsightLegacySourceSyncResponse:
        rows = list(
            (
                await db.exec(
                    select(InsightDataSource)
                    .where(InsightDataSource.is_deleted == 0)
                    .order_by(InsightDataSource.id.asc())
                    .limit(5000)
                )
            ).all()
        )
        response = InsightLegacySourceSyncResponse(checked_count=len(rows))
        legacy_config_count_before = await self._count_legacy_configs(db)
        channels = list((await db.exec(select(InsightChannel).where(InsightChannel.is_deleted == 0))).all())
        config_cache: dict[str, int] = {}
        channel_cache: dict[int, int | None] = {}
        for row in rows:
            changed = False
            legacy_linked = False
            if not row.monitor_config_id:
                config_id = await self._legacy_monitor_config_id(db, row, user_id=user_id, cache=config_cache)
                if config_id:
                    row.monitor_config_id = config_id
                    response.linked_source_count += 1
                    legacy_linked = True
                    changed = True
            if not row.monitor_object_type:
                row.monitor_object_type = "company" if row.company_id else "topic"
                changed = True
            if row.monitor_object_id is None and row.company_id:
                row.monitor_object_id = row.company_id
                changed = True
            if not row.execution_role:
                row.execution_role = self._execution_role_for_source_type(row.source_type)
                response.updated_role_count += 1
                changed = True
            if not row.collection_strategy:
                row.collection_strategy = "standard"
                changed = True
            if legacy_linked and (not row.generation_mode or row.generation_mode == "manual"):
                row.generation_mode = "legacy_migrated"
                changed = True
            if not row.channel_id:
                cached = channel_cache.get(row.id or 0)
                channel_id = cached if (row.id or 0) in channel_cache else self._match_channel_id(row, channels)
                channel_cache[row.id or 0] = channel_id
                if channel_id:
                    row.channel_id = channel_id
                    response.linked_channel_count += 1
                    changed = True
            if changed:
                row.update_by = str(user_id) if user_id else None
                row.update_time = datetime.now()
            else:
                response.skipped_count += 1
        if rows:
            await db.commit()
        legacy_config_count_after = await self._count_legacy_configs(db)
        response.created_config_count = max(legacy_config_count_after - legacy_config_count_before, 0)
        return response

    async def execute_data_source(
        self,
        db: AsyncSession,
        data_source_id: int,
        payload: InsightDataSourceExecuteRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightDataSourceExecuteResponse:
        row = await self._get_data_source(db, data_source_id, user_id=user_id, is_admin=is_admin, permission="edit")
        if row.status != "enabled":
            raise ValueError("数据源未启用，不能执行采集")
        config = self._normalize_fetch_config(row.fetch_config)
        row.last_fetch_time = datetime.now()
        await db.commit()

        if row.source_type in {"official_site", "web_page"}:
            if not row.base_url:
                raise ValueError("网页类数据源必须配置 URL")
            manual_result = await insight_crawl_service.crawl_manual_url(
                db,
                InsightManualUrlCrawlRequest(
                    url=row.base_url,
                    query_text=payload.keyword or self._first_keyword(config) or row.source_name,
                    data_source_id=row.id,
                ),
                user_id,
                is_admin=is_admin,
            )
            row.last_success_time = datetime.now()
            await db.commit()
            await db.refresh(row)
            auto_review_summary = await self._apply_auto_candidate_policy(
                db,
                row,
                [manual_result.candidate],
                config,
                user_id,
                is_admin=is_admin,
            )
            return InsightDataSourceExecuteResponse(
                data_source=await self._to_read_with_company(db, row),
                manual_result=manual_result,
                auto_review_summary=auto_review_summary,
            )

        keywords = [payload.keyword.strip()] if payload.keyword and payload.keyword.strip() else self._string_list(config.get("keywords"))
        if not keywords:
            raise ValueError("搜索类数据源必须至少配置一个关键词")
        max_results = int(config.get("max_results") or 8)
        configured_crawl_top_n = config.get("crawl_top_n")
        crawl_top_n = (
            payload.crawl_top_n
            if payload.crawl_top_n is not None
            else int(configured_crawl_top_n if configured_crawl_top_n is not None else max_results)
        )
        crawl_top_n = min(max(crawl_top_n, 0), max_results)
        search_results = []
        execution_errors: list[dict[str, str]] = []
        for query in self._dedupe_keywords(keywords):
            try:
                search_results.append(
                    await insight_search_discovery_service.search_and_crawl(
                        db,
                        InsightSearchDiscoveryRequest(
                            query=query,
                            channels=self._channels_for_source_type(row.source_type),
                            freshness=config.get("freshness") or "noLimit",
                            max_results=max_results,
                            crawl_top_n=crawl_top_n,
                            data_source_id=row.id,
                            include_keywords=self._string_list(config.get("include_keywords")),
                            exclude_keywords=self._string_list(config.get("exclude_keywords")),
                            filter_prompt=config.get("filter_prompt"),
                            enable_llm_filter=bool(config.get("enable_llm_filter")),
                            llm_min_score=float(config.get("llm_min_score") if config.get("llm_min_score") is not None else 0.6),
                            create_candidate_from_hits=bool(config.get("create_candidate_from_hits")),
                        ),
                        user_id,
                        is_admin=is_admin,
                    )
                )
            except Exception as exc:
                execution_errors.append({"keyword": query, "error": str(exc)})
        if not search_results and execution_errors:
            raise ValueError(f"全部关键词采集失败：{execution_errors[0]['error']}")
        if search_results:
            row.last_success_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        auto_review_summary = await self._apply_auto_candidate_policy(
            db,
            row,
            [candidate for result in search_results for candidate in result.candidates],
            config,
            user_id,
            is_admin=is_admin,
        )
        return InsightDataSourceExecuteResponse(
            data_source=await self._to_read_with_company(db, row),
            search_result=search_results[0] if search_results else None,
            search_results=search_results,
            execution_errors=execution_errors,
            auto_review_summary=auto_review_summary,
        )

    async def _apply_auto_candidate_policy(
        self,
        db: AsyncSession,
        row: InsightDataSource,
        candidates: list,
        config: dict,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> dict:
        _ = db, row, config, user_id, is_admin
        items: list[dict] = []
        formal_count = 0
        candidate_count = 0
        noise_count = 0
        failed_count = 0
        for candidate in candidates:
            candidate_id = getattr(candidate, "id", None)
            status = str(getattr(candidate, "review_status", "") or "")
            if not candidate_id:
                failed_count += 1
                continue
            if status == "promoted":
                formal_count += 1
                action = "formal"
            elif status == "ignored":
                noise_count += 1
                action = "noise"
            elif status == "pending":
                candidate_count += 1
                action = "candidate"
            else:
                failed_count += 1
                action = status or "unknown"
            items.append(
                {
                    "candidate_id": candidate_id,
                    "action": action,
                    "status": status,
                    "confidence": float(getattr(candidate, "confidence", 0) or 0),
                    "title": str(getattr(candidate, "candidate_title", "") or "")[:120],
                }
            )

        return {
            "enabled": True,
            "mode": "ai_auto_review",
            "checked_count": len(candidates),
            "formal_count": formal_count,
            "candidate_count": candidate_count,
            "noise_count": noise_count,
            "failed_count": failed_count,
            "items": items[:50],
        }

    def _auto_review_decision(
        self,
        candidate,
        *,
        mode: str,
        min_confidence: float,
        required_tags: set[str],
        allowed_types: set[str],
    ) -> dict:
        confidence = float(getattr(candidate, "confidence", 0) or 0)
        candidate_type = str(getattr(candidate, "intelligence_type", "") or "").strip()
        tags = self._candidate_tag_names(getattr(candidate, "suggested_tags", None))
        if mode == "high_confidence" and confidence < min_confidence:
            return {"passed": False, "reason": f"置信度 {confidence:.2f} 低于阈值 {min_confidence:.2f}"}
        if required_tags and tags.isdisjoint(required_tags):
            return {"passed": False, "reason": f"未命中必需标签：{'、'.join(sorted(required_tags))}"}
        if allowed_types and candidate_type not in allowed_types:
            return {"passed": False, "reason": f"情报类型不在自动通过范围：{candidate_type or '未识别'}"}
        return {"passed": True, "reason": "符合自动审核策略"}

    def _candidate_tag_names(self, value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        result: set[str] = set()
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("tag") or "").strip()
            else:
                name = str(item or "").strip()
            if name:
                result.add(name)
        return result

    def _float_config(self, value: object, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return min(max(parsed, 0), 1)

    async def _get_data_source(
        self,
        db: AsyncSession,
        data_source_id: int,
        *,
        user_id: int | None = None,
        is_admin: bool = True,
        permission: str = "view",
    ) -> InsightDataSource:
        filters = [InsightDataSource.id == data_source_id, InsightDataSource.is_deleted == 0]
        filters.append(
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
                permission=permission,
            )
        )
        filters.append(await self._data_source_company_scope_filter(db, user_id=user_id, is_admin=is_admin))
        row = (await db.exec(select(InsightDataSource).where(*filters))).first()
        if not row:
            raise ValueError("数据源不存在或无权访问")
        return row

    async def _data_source_company_scope_filter(self, db: AsyncSession, *, user_id: int | None, is_admin: bool):
        if is_admin:
            return True
        sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
        if sys_company_id is None:
            return InsightDataSource.company_id.is_(None)
        return or_(
            InsightDataSource.company_id.is_(None),
            exists()
            .where(
                and_(
                    InsightCompany.id == InsightDataSource.company_id,
                    InsightCompany.sys_company_id == sys_company_id,
                    InsightCompany.is_deleted == 0,
                )
            )
            .correlate(InsightDataSource),
        )

    async def _ensure_company_access(self, db: AsyncSession, company_id: int | None, *, user_id: int | None, is_admin: bool) -> None:
        if is_admin or company_id is None:
            return
        sys_company_id = await insight_permission_service.resolve_user_sys_company_id(db, user_id)
        company = (
            await db.exec(
                select(InsightCompany).where(
                    InsightCompany.id == company_id,
                    InsightCompany.is_deleted == 0,
                )
            )
        ).first()
        if not company:
            raise ValueError("关联企业不存在")
        if sys_company_id is None or company.sys_company_id != sys_company_id:
            raise ValueError("无权为其他所属公司的企业配置数据源")

    async def _ensure_monitor_config_exists(self, db: AsyncSession, monitor_config_id: int | None) -> None:
        if monitor_config_id is None:
            return
        exists_row = (
            await db.exec(
                select(InsightMonitorConfig.id).where(
                    InsightMonitorConfig.id == monitor_config_id,
                    InsightMonitorConfig.is_deleted == 0,
                )
            )
        ).first()
        if not exists_row:
            raise ValueError("关联监测配置不存在")

    async def _ensure_channel_exists(self, db: AsyncSession, channel_id: int | None) -> None:
        if channel_id is None:
            return
        exists_row = (
            await db.exec(
                select(InsightChannel.id).where(
                    InsightChannel.id == channel_id,
                    InsightChannel.is_deleted == 0,
                )
            )
        ).first()
        if not exists_row:
            raise ValueError("关联渠道不存在")

    async def _ensure_company_monitor_config(
        self,
        db: AsyncSession,
        company: InsightCompany,
        *,
        user_id: int | None,
        generation_mode: str,
    ) -> int:
        code = f"company_{company.id}_default"
        existing = (await db.exec(select(InsightMonitorConfig).where(InsightMonitorConfig.config_code == code))).first()
        if existing:
            if existing.is_deleted:
                existing.is_deleted = 0
                existing.status = "active"
            return existing.id or 0
        relation_type = company.company_type or "其他"
        row = InsightMonitorConfig(
            config_code=code,
            config_name=f"{company.short_name or company.name}企业监测",
            monitor_type="enterprise",
            object_type="company",
            object_id=company.id,
            object_name=company.name,
            relation_type=relation_type,
            enabled_modules=["企业新闻", "官网动态", "经营财经", "专利技术", "电商新品"],
            keywords=[company.name, company.short_name] if company.short_name else [company.name],
            excluded_keywords=["招聘", "广告招商"],
            monitor_strength="standard",
            fetch_frequency="daily",
            ai_review_prompt=self._default_company_prompt(relation_type),
            ai_review_policy="ai_auto",
            owner_user_id=user_id,
            visibility_scope="assigned",
            generation_mode=generation_mode,
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(row)
        await db.flush()
        return row.id or 0

    async def _legacy_monitor_config_id(
        self,
        db: AsyncSession,
        row: InsightDataSource,
        *,
        user_id: int | None,
        cache: dict[str, int],
    ) -> int | None:
        if row.company_id:
            company = await db.get(InsightCompany, row.company_id)
            if company:
                cache_key = f"company:{company.id}"
                if cache_key not in cache:
                    cache[cache_key] = await self._ensure_company_monitor_config(
                        db,
                        company,
                        user_id=user_id,
                        generation_mode="legacy_migrated",
                    )
                return cache[cache_key]
        role = self._execution_role_for_source_type(row.source_type)
        cache_key = f"topic:{role}"
        if cache_key in cache:
            return cache[cache_key]
        code = f"legacy_topic_{role}"[:80]
        existing = (await db.exec(select(InsightMonitorConfig).where(InsightMonitorConfig.config_code == code))).first()
        if existing:
            if existing.is_deleted:
                existing.is_deleted = 0
                existing.status = "active"
            cache[cache_key] = existing.id or 0
            return cache[cache_key]
        row_config = InsightMonitorConfig(
            config_code=code,
            config_name=f"历史迁移-{self._execution_role_label(role)}",
            monitor_type=self._monitor_type_for_role(role),
            object_type="topic",
            object_name=self._execution_role_label(role),
            enabled_modules=[self._execution_role_label(role)],
            keywords=[],
            excluded_keywords=["招聘", "广告招商"],
            monitor_strength="standard",
            fetch_frequency=row.fetch_frequency or "daily",
            ai_review_prompt=self._default_topic_prompt(role),
            ai_review_policy="ai_auto",
            owner_user_id=user_id,
            visibility_scope=row.visibility_scope or "assigned",
            generation_mode="legacy_migrated",
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(row_config)
        await db.flush()
        cache[cache_key] = row_config.id or 0
        return cache[cache_key]

    async def _count_legacy_configs(self, db: AsyncSession) -> int:
        return (
            await db.exec(
                select(func.count())
                .select_from(InsightMonitorConfig)
                .where(InsightMonitorConfig.is_deleted == 0, InsightMonitorConfig.generation_mode == "legacy_migrated")
            )
        ).one()

    def _channels_for_source_type(self, source_type: str) -> list[str]:
        mapping = {
            "baidu_news": ["baidu_news"],
            "baidu_search": ["baidu"],
            "bocha_search": ["bocha"],
            "bocha_news": ["bocha_news"],
            "bocha_web": ["bocha"],
            "multi_news": ["baidu_news"],
            "wechat_public_account": ["baidu_news"],
            "ecommerce_search": ["baidu_news"],
            "government_policy": ["baidu_news"],
            "finance_news": ["baidu_news"],
            "patent_search": ["baidu_news"],
            "industry_media": ["baidu_news"],
        }
        return mapping.get(source_type, ["baidu_news"])

    def _build_batch_fetch_config(
        self,
        payload: InsightDataSourceBatchCreateRequest,
        company: InsightCompany,
        source_type: str,
    ) -> dict:
        company_name = company.name
        company_short_name = company.short_name or company.name
        keyword_template = (payload.keyword_template or "").strip()
        if keyword_template:
            keywords = [
                keyword_template
                .replace("{企业}", company_name)
                .replace("{简称}", company_short_name)
                .replace("{类型}", self._source_type_label(source_type))
            ]
        else:
            keywords = self._default_keywords_for_source_type(company_name, company_short_name, source_type)
        config = InsightDataSourceFetchConfig(
            keywords=keywords,
            include_keywords=payload.include_keywords,
            exclude_keywords=payload.exclude_keywords,
            max_results=payload.max_results,
            crawl_top_n=payload.crawl_top_n,
            freshness=payload.freshness,
            schedule_type=payload.fetch_frequency,
            enable_llm_filter=payload.enable_llm_filter,
            filter_prompt=payload.filter_prompt or self._default_filter_prompt(source_type),
            llm_min_score=0.6,
            llm_failure_policy="keep",
            auto_review_mode=payload.auto_review_mode,
            auto_review_min_confidence=payload.auto_review_min_confidence,
            auto_add_to_report_pool=payload.auto_add_to_report_pool,
            auto_report_folder=payload.auto_report_folder,
            create_candidate_from_hits=True,
            extra={
                "batch_generated": True,
                "company_id": company.id,
                "source_type_label": self._source_type_label(source_type),
                "generated_strategy": "multi_company_multi_type",
            },
        ).model_dump()
        return self._normalize_fetch_config(config)

    def _default_keywords_for_source_type(self, company_name: str, company_short_name: str, source_type: str) -> list[str]:
        name = company_short_name or company_name
        mapping = {
            "multi_news": [f"{name} 新品 OR 市场 OR 合作 OR 扩产 OR 价格"],
            "wechat_public_account": [f"{name} 公众号 新品 市场 合作"],
            "ecommerce_search": [f"{name} 新品 旗舰店 配料 规格 价格"],
            "government_policy": [f"{company_name} 政策 公示 许可 监管 标准"],
            "finance_news": [f"{company_name} 业绩 投资 融资 财报 经营"],
            "patent_search": [f"{company_name} 专利 技术 配方 工艺"],
            "industry_media": [f"{name} 食品饮料 行业 新品 趋势"],
            "baidu_news": [f"{name} 新闻 新品 市场"],
            "baidu_search": [f"{name} 新品 市场 竞品"],
            "bocha_search": [f"{name} 新闻 新品 市场 竞品"],
            "bocha_news": [f"{name} 新闻 新品 市场"],
            "bocha_web": [f"{name} 新品 市场 竞品"],
        }
        return mapping.get(source_type, [f"{name} 新品 市场 动态"])

    def _default_filter_prompt(self, source_type: str) -> str:
        base = "保留与食品饮料、功能糖、淀粉糖、植物蛋白、配料原料、客户/竞对动态、政策法规、专利技术、研发营销机会相关的公开信息；过滤验证码、图片搜索、百科泛信息、无业务价值页面和明显跨行业噪声。"
        additions = {
            "ecommerce_search": "重点关注新品、规格、配料表、价格带、卖点、渠道和用户反馈。",
            "patent_search": "重点关注专利标题、申请人、技术方案、配方工艺和研发方向。",
            "government_policy": "重点关注政策、标准、监管、公示、许可和产业扶持。",
            "finance_news": "重点关注经营变化、财务表现、投融资、产能、价格和供应链。",
            "wechat_public_account": "重点关注品牌官方或行业号发布的新品、活动、渠道和研发营销信息。",
            "industry_media": "重点关注行业趋势、竞对动作、产品创新和渠道变化。",
        }
        return f"{base}{additions.get(source_type, '')}"

    def _source_type_label(self, source_type: str) -> str:
        labels = {
            "baidu_news": "百度资讯",
            "baidu_search": "百度搜索",
            "bocha_search": "博查搜索",
            "bocha_news": "博查资讯",
            "bocha_web": "博查网页",
            "multi_news": "综合动态",
            "wechat_public_account": "公众号",
            "ecommerce_search": "电商新品",
            "government_policy": "政策监管",
            "finance_news": "经营财经",
            "patent_search": "专利技术",
            "industry_media": "行业媒体",
            "official_site": "官网",
            "web_page": "网页",
        }
        return labels.get(source_type, source_type)

    def _execution_role_for_source_type(self, source_type: str) -> str:
        mapping = {
            "official_site": "官网动态",
            "web_page": "官网动态",
            "finance_news": "经营财经",
            "patent_search": "专利技术",
            "government_policy": "政策监管",
            "ecommerce_search": "电商新品",
            "industry_media": "行业资讯",
            "wechat_public_account": "企业新闻",
            "multi_news": "企业新闻",
            "baidu_news": "企业新闻",
            "baidu_search": "综合舆情",
            "bocha_search": "综合舆情",
            "bocha_news": "企业新闻",
            "bocha_web": "综合舆情",
        }
        return mapping.get(source_type, "综合舆情")

    def _execution_role_label(self, role: str) -> str:
        labels = {
            "企业新闻": "企业新闻",
            "官网动态": "官网动态",
            "经营财经": "经营财经",
            "专利技术": "专利技术",
            "技术专利": "技术专利",
            "电商新品": "电商新品",
            "行业资讯": "行业资讯",
            "政策监管": "政策监管",
            "综合舆情": "综合舆情",
        }
        return labels.get(role, self._source_type_label(role))

    def _monitor_type_for_role(self, role: str) -> str:
        if role in {"企业新闻", "官网动态", "经营财经", "电商新品"}:
            return "enterprise"
        if role in {"政策监管"}:
            return "policy"
        if role in {"专利技术", "技术专利"}:
            return "technology"
        if role in {"行业资讯"}:
            return "industry"
        return "public_opinion"

    def _default_topic_prompt(self, role: str) -> str:
        base = "你是研发营销市场洞察平台的情报评审助手。请判断公开资料是否对我司研发、销售、客户经营、产品机会、竞对动态或战略判断有实际参考价值。"
        additions = {
            "行业资讯": "重点保留行业趋势、产品创新、消费变化、渠道变化和原料应用信息。",
            "政策监管": "重点保留政策法规、监管通报、标准发布、许可公示和产业扶持信息。",
            "专利技术": "重点保留专利申请、技术路线、配方工艺、研发方向和可借鉴方案。",
            "技术专利": "重点保留专利申请、技术路线、配方工艺、研发方向和可借鉴方案。",
            "经营财经": "重点保留经营变化、投融资、产能、财报、价格和供应链信号。",
            "电商新品": "重点保留新品、卖点、规格、配料、价格带、渠道和用户反馈。",
            "企业新闻": "重点保留企业新品、合作、扩产、渠道、风险和市场动作。",
        }
        return f"{base}{additions.get(role, '过滤重复转载、百科泛信息、广告招商、招聘和无业务价值内容。')}"

    def _default_company_prompt(self, relation_type: str | None) -> str:
        relation = (relation_type or "").strip()
        if relation == "竞对":
            return "当前企业是我司竞对。请重点保留新品发布、技术专利、价格策略、渠道动作、营销活动、产能扩张、客户合作、融资并购、战略方向、风险事件等信息；无关转载、低价值财经快讯、重复内容和泛泛介绍不进入正式情报。"
        if relation in {"潜在客户", "客户"}:
            return "当前企业是我司客户或潜在客户。请重点保留新品上市、配方变化、采购需求、产能扩张、渠道布局、经营变化、质量风险、政策影响、合作动态和供应链变化；与业务机会无关的信息不进入正式情报。"
        if relation == "供应商":
            return "当前企业是我司供应商或潜在供应商。请重点识别价格波动、产能变化、交付风险、质量风险、环保安全、政策影响、财务经营和替代供应可能性。"
        return "当前企业是我司关注对象。请保留与研发、营销、销售、客户经营、供应链、政策、专利、产品和战略判断相关的信息；过滤重复、泛泛、广告、招聘和低价值内容。"

    def _match_channel_id(self, row: InsightDataSource, channels: list[InsightChannel]) -> int | None:
        text = " ".join([row.source_name or "", row.source_code or "", row.base_url or ""]).lower()
        if not text:
            return None
        for channel in channels:
            if channel.channel_url and row.base_url and self._same_domain(channel.channel_url, row.base_url):
                return channel.id
        for channel in channels:
            name = (channel.channel_name or "").lower()
            code = (channel.channel_code or "").lower()
            if name and name in text:
                return channel.id
            if code and code in text:
                return channel.id
        role = self._execution_role_for_source_type(row.source_type)
        candidates = [
            channel
            for channel in channels
            if role in (channel.applicable_scenarios or []) and channel.access_status in {"supported", "partial", "pending"}
        ]
        return candidates[0].id if candidates and candidates[0].id else None

    def _same_domain(self, left: str, right: str) -> bool:
        def domain(value: str) -> str:
            text = value.lower().replace("https://", "").replace("http://", "").split("/", 1)[0]
            return text[4:] if text.startswith("www.") else text

        left_domain = domain(left)
        right_domain = domain(right)
        return bool(left_domain and right_domain and (left_domain == right_domain or left_domain in right_domain or right_domain in left_domain))

    def _batch_source_code(self, company_id: int, source_type: str) -> str:
        return f"batch_{company_id}_{source_type}"[:64]

    def _dedupe_ints(self, values: list[int]) -> list[int]:
        result: list[int] = []
        seen: set[int] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _resolve_schedule_enabled(self, fetch_frequency: str | None, value: bool | None) -> bool:
        if value is not None:
            return value and fetch_frequency != "manual"
        return fetch_frequency not in {None, "", "manual"}

    def _calculate_next_run_time(
        self,
        fetch_frequency: str | None,
        fetch_config: dict | None,
        base_time: datetime,
    ) -> datetime | None:
        frequency = fetch_frequency or "manual"
        if frequency == "manual":
            return None
        if frequency == "15m":
            return base_time + timedelta(minutes=15)
        if frequency == "hourly":
            return base_time + timedelta(hours=1)
        if frequency == "weekly":
            return base_time + timedelta(days=7)
        if frequency == "cron":
            cron_expression = (fetch_config or {}).get("cron_expression")
            return self._next_cron_time(str(cron_expression or ""), base_time) or (base_time + timedelta(days=1))
        return base_time + timedelta(days=1)

    def _schedule_source_timeout_seconds(self, fetch_config: dict | None) -> int:
        config = fetch_config or {}
        keywords = self._string_list(config.get("keywords"))
        keyword_count = max(1, min(len(keywords), 5))
        max_results = min(max(int(config.get("max_results") or 4), 1), 20)
        crawl_top_n = int(config.get("crawl_top_n") if config.get("crawl_top_n") is not None else max_results)
        per_keyword = settings.INSIGHT_SEARCH_TIMEOUT_SECONDS + 10
        if crawl_top_n > 0:
            per_keyword += min(crawl_top_n, max_results) * (settings.INSIGHT_FIRECRAWL_TIMEOUT_SECONDS + 5)
        return max(45, min(keyword_count * per_keyword, 240))

    def _next_cron_time(self, cron_expression: str, base_time: datetime) -> datetime | None:
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            return None
        minute_part, hour_part, day_part, month_part, weekday_part = parts
        if day_part != "*" or month_part != "*" or weekday_part != "*":
            return None
        minutes = self._cron_values(minute_part, 0, 59)
        hours = self._cron_values(hour_part, 0, 23)
        if not minutes or not hours:
            return None
        cursor = base_time.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = base_time + timedelta(days=2)
        while cursor <= end:
            if cursor.minute in minutes and cursor.hour in hours:
                return cursor
            cursor += timedelta(minutes=1)
        return None

    def _cron_values(self, value: str, start: int, end: int) -> set[int]:
        if value == "*":
            return set(range(start, end + 1))
        if value.startswith("*/"):
            try:
                step = int(value[2:])
            except ValueError:
                return set()
            if step <= 0:
                return set()
            return set(range(start, end + 1, step))
        result: set[int] = set()
        for item in value.split(","):
            try:
                parsed = int(item)
            except ValueError:
                return set()
            if start <= parsed <= end:
                result.add(parsed)
        return result

    def _normalize_fetch_config(self, value: object) -> dict:
        if isinstance(value, InsightDataSourceFetchConfig):
            return value.model_dump()
        if isinstance(value, dict):
            return InsightDataSourceFetchConfig(**value).model_dump()
        return InsightDataSourceFetchConfig().model_dump()

    def _validate_data_source_config(
        self,
        *,
        source_type: str,
        base_url: str | None,
        fetch_frequency: str | None,
        fetch_config: dict | None,
        schedule_enabled: bool | None,
        status: str | None,
        visibility_scope: str | None,
        generation_mode: str | None = None,
        collection_strategy: str | None = None,
    ) -> None:
        config = fetch_config or {}
        source_type = (source_type or "").strip()
        frequency = (fetch_frequency or "manual").strip()
        current_status = (status or "enabled").strip()
        visibility = (visibility_scope or "private").strip()
        mode = (generation_mode or "manual").strip()
        strategy = (collection_strategy or "standard").strip()
        if source_type not in self.allowed_source_types:
            raise ValueError(f"数据源类型不支持：{source_type or '未填写'}")
        if frequency not in self.allowed_fetch_frequencies:
            raise ValueError(f"抓取周期不支持：{frequency or '未填写'}")
        if current_status not in self.allowed_statuses:
            raise ValueError(f"数据源状态不支持：{current_status or '未填写'}")
        if visibility not in self.allowed_visibility_scopes:
            raise ValueError(f"可见范围不支持：{visibility or '未填写'}")
        if mode not in self.allowed_generation_modes:
            raise ValueError(f"生成方式不支持：{mode or '未填写'}")
        if strategy not in self.allowed_collection_strategies:
            raise ValueError(f"采集策略不支持：{strategy or '未填写'}")

        enabled = current_status == "enabled"
        if enabled and source_type in self.web_source_types and not (base_url or "").strip():
            raise ValueError("网页类数据源启用前必须配置 URL")

        max_results = self._positive_int_config(config, "max_results", "发现数量", default=8, minimum=1, maximum=20)
        crawl_top_n = self._positive_int_config(config, "crawl_top_n", "每词抓取上限", default=max_results, minimum=0, maximum=20)
        if crawl_top_n > max_results:
            raise ValueError("每词抓取上限不能大于发现数量")

        effective_schedule_enabled = self._resolve_schedule_enabled(frequency, schedule_enabled)
        if effective_schedule_enabled and source_type not in self.web_source_types and not self._string_list(config.get("keywords")):
            raise ValueError("周期采集的搜索类数据源必须至少配置一个独立搜索关键词")
        if effective_schedule_enabled and frequency == "cron":
            cron_expression = str(config.get("cron_expression") or "").strip()
            if not cron_expression or self._next_cron_time(cron_expression, datetime.now()) is None:
                raise ValueError("自定义 Cron 周期必须填写可解析的 5 段表达式")

        if bool(config.get("enable_llm_filter")) and not str(config.get("filter_prompt") or "").strip():
            raise ValueError("启用 LLM 筛选时必须填写筛选提示词")

        auto_review_mode = str(config.get("auto_review_mode") or "off")
        if auto_review_mode not in self.allowed_auto_review_modes:
            raise ValueError(f"自动审核模式不支持：{auto_review_mode}")

    def _positive_int_config(self, config: dict, key: str, label: str, *, default: int, minimum: int, maximum: int) -> int:
        raw_value = config.get(key)
        if raw_value in (None, ""):
            return default
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}必须是数字") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"{label}必须在 {minimum}-{maximum} 之间")
        return value

    def _first_keyword(self, config: dict) -> str | None:
        keywords = self._string_list(config.get("keywords"))
        return keywords[0] if keywords else None

    def _dedupe_keywords(self, keywords: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            key = keyword.strip()
            normalized = key.lower()
            if key and normalized not in seen:
                seen.add(normalized)
                result.append(key)
        return result

    def _string_list(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in value.splitlines() if item.strip()]
        return []

    async def _to_read_with_company(self, db: AsyncSession, row: InsightDataSource) -> InsightDataSourceRead:
        company = await db.get(InsightCompany, row.company_id) if row.company_id else None
        channel = await db.get(InsightChannel, row.channel_id) if row.channel_id else None
        monitor_config = await db.get(InsightMonitorConfig, row.monitor_config_id) if row.monitor_config_id else None
        return self._to_read(row, company, channel, monitor_config)

    def _to_read(
        self,
        row: InsightDataSource,
        company: InsightCompany | None = None,
        channel: InsightChannel | None = None,
        monitor_config: InsightMonitorConfig | None = None,
    ) -> InsightDataSourceRead:
        return InsightDataSourceRead(
            id=row.id,
            create_time=row.create_time,
            update_time=row.update_time,
            create_by=row.create_by,
            update_by=row.update_by,
            comment=row.comment,
            is_deleted=row.is_deleted,
            source_code=row.source_code,
            source_name=row.source_name,
            source_type=row.source_type,
            base_url=row.base_url,
            channel_id=row.channel_id,
            channel_name=channel.channel_name if channel else None,
            monitor_config_id=row.monitor_config_id,
            monitor_config_name=monitor_config.config_name if monitor_config else None,
            monitor_object_type=row.monitor_object_type,
            monitor_object_id=row.monitor_object_id,
            execution_role=row.execution_role,
            generation_mode=row.generation_mode,
            collection_strategy=row.collection_strategy,
            company_id=row.company_id,
            company_name=company.name if company else None,
            company_short_name=company.short_name if company else None,
            fetch_frequency=row.fetch_frequency,
            fetch_config=row.fetch_config,
            auth_config_ref=row.auth_config_ref,
            last_fetch_time=row.last_fetch_time,
            last_success_time=row.last_success_time,
            next_run_time=row.next_run_time,
            schedule_enabled=row.schedule_enabled,
            last_schedule_status=row.last_schedule_status,
            last_schedule_message=row.last_schedule_message,
            consecutive_failure_count=row.consecutive_failure_count or 0,
            last_failure_time=row.last_failure_time,
            auto_paused_reason=row.auto_paused_reason,
            owner_user_id=row.owner_user_id,
            owner_dept_id=row.owner_dept_id,
            visibility_scope=row.visibility_scope,
            status=row.status,
        )

    def _to_task_read(self, row: InsightTask) -> InsightTaskRead:
        return InsightTaskRead(
            id=row.id,
            create_time=row.create_time,
            update_time=row.update_time,
            create_by=row.create_by,
            update_by=row.update_by,
            comment=row.comment,
            is_deleted=row.is_deleted,
            task_uid=row.task_uid,
            task_type=row.task_type,
            data_source_id=row.data_source_id,
            intelligence_id=row.intelligence_id,
            report_id=row.report_id,
            status=row.status.value,
            progress=row.progress,
            started_at=row.started_at,
            finished_at=row.finished_at,
            retry_count=row.retry_count,
            input_payload=row.input_payload,
            output_payload=row.output_payload,
            error_message=row.error_message,
        )


insight_data_source_service = InsightDataSourceService()
