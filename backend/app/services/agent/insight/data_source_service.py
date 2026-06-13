from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.agent.insight import InsightCompany, InsightDataSource, InsightTask, InsightTaskStatus
from app.schemas.agent.insight.crawl import InsightManualUrlCrawlRequest, InsightSearchDiscoveryRequest
from app.schemas.agent.insight.data_source import (
    InsightDataSourceCreate,
    InsightDataSourceExecuteRequest,
    InsightDataSourceExecuteResponse,
    InsightDataSourceFetchConfig,
    InsightDataSourceRead,
    InsightDataSourceScheduleExecution,
    InsightDataSourceScheduleRunResponse,
    InsightDataSourceUpdate,
    InsightStaleTaskCleanupResponse,
)
from app.schemas.agent.insight.intelligence import InsightCandidatePromoteRequest, InsightPoolUpsertRequest
from app.schemas.agent.insight.task import InsightTaskRead
from app.schemas.page import Page
from app.services.agent.insight.crawler import insight_crawl_service, insight_search_discovery_service
from app.services.agent.insight.intelligence_service import insight_intelligence_service
from app.services.agent.insight.permission_service import insight_permission_service


class InsightDataSourceService:
    allowed_source_types = {"baidu_news", "baidu_search", "bocha_news", "bocha_web", "multi_news", "official_site", "web_page"}
    web_source_types = {"official_site", "web_page"}
    allowed_fetch_frequencies = {"manual", "15m", "hourly", "daily", "weekly", "cron"}
    allowed_statuses = {"enabled", "disabled"}
    allowed_visibility_scopes = {"private", "assigned", "dept", "role", "public"}
    allowed_auto_review_modes = {"off", "high_confidence", "all"}

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
                result = await self.execute_data_source(
                    db,
                    row.id or 0,
                    InsightDataSourceExecuteRequest(),
                    user_id,
                    is_admin=True,
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
        filters.append(
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
            )
        )

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
        )
        row = InsightDataSource(
            source_code=source_code,
            source_name=payload.source_name,
            source_type=payload.source_type,
            base_url=payload.base_url,
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
        self._validate_data_source_config(
            source_type=data.get("source_type", row.source_type),
            base_url=data.get("base_url", row.base_url),
            fetch_frequency=data.get("fetch_frequency", row.fetch_frequency),
            fetch_config=data.get("fetch_config", row.fetch_config),
            schedule_enabled=data.get("schedule_enabled", row.schedule_enabled),
            status=data.get("status", row.status),
            visibility_scope=data.get("visibility_scope", row.visibility_scope),
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
        crawl_top_n = payload.crawl_top_n if payload.crawl_top_n is not None else int(config.get("crawl_top_n") or max_results)
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
        mode = str(config.get("auto_review_mode") or "off")
        if mode not in {"high_confidence", "all"}:
            return {
                "enabled": False,
                "mode": mode,
                "checked_count": len(candidates),
                "promoted_count": 0,
                "pooled_count": 0,
                "skipped_count": len(candidates),
                "items": [],
            }

        min_confidence = self._float_config(config.get("auto_review_min_confidence"), 0.75)
        required_tags = {item.strip() for item in self._string_list(config.get("auto_review_required_tags"))}
        allowed_types = {item.strip() for item in self._string_list(config.get("auto_review_intelligence_types"))}
        auto_pool = bool(config.get("auto_add_to_report_pool"))
        folder_name = str(config.get("auto_report_folder") or "").strip() or None
        items: list[dict] = []
        promoted_count = 0
        pooled_count = 0
        skipped_count = 0

        for candidate in candidates:
            candidate_id = getattr(candidate, "id", None)
            if not candidate_id:
                skipped_count += 1
                continue
            decision = self._auto_review_decision(
                candidate,
                mode=mode,
                min_confidence=min_confidence,
                required_tags=required_tags,
                allowed_types=allowed_types,
            )
            if not decision["passed"]:
                skipped_count += 1
                items.append({"candidate_id": candidate_id, "action": "skip", "reason": decision["reason"]})
                continue

            try:
                response = await insight_intelligence_service.promote_candidate(
                    db,
                    candidate_id,
                    InsightCandidatePromoteRequest(
                        visibility_scope="assigned",
                        importance_level="medium",
                        review_comment=f"数据源策略自动通过：{row.source_name}",
                    ),
                    user_id,
                    is_admin=is_admin,
                )
                promoted_count += 1
                intelligence_id = response.intelligence.id if response.intelligence else None
                pooled = False
                if auto_pool and intelligence_id and user_id is not None:
                    await insight_intelligence_service.upsert_user_pool(
                        db,
                        intelligence_id,
                        InsightPoolUpsertRequest(
                            pool_type="report_material",
                            folder_name=folder_name,
                            note=f"数据源策略自动加入报告素材池：{row.source_name}",
                        ),
                        user_id=user_id,
                    )
                    pooled = True
                    pooled_count += 1
                items.append({"candidate_id": candidate_id, "action": "promote", "intelligence_id": intelligence_id, "pooled": pooled})
            except Exception as exc:
                skipped_count += 1
                items.append({"candidate_id": candidate_id, "action": "error", "reason": str(exc)})

        return {
            "enabled": True,
            "mode": mode,
            "checked_count": len(candidates),
            "promoted_count": promoted_count,
            "pooled_count": pooled_count,
            "skipped_count": skipped_count,
            "min_confidence": min_confidence,
            "auto_add_to_report_pool": auto_pool,
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
        row = (await db.exec(select(InsightDataSource).where(*filters))).first()
        if not row:
            raise ValueError("数据源不存在或无权访问")
        return row

    def _channels_for_source_type(self, source_type: str) -> list[str]:
        mapping = {
            "baidu_news": ["baidu_news"],
            "baidu_search": ["baidu"],
            "bocha_news": ["bocha_news"],
            "bocha_web": ["bocha"],
            "multi_news": ["baidu_news", "bocha_news"],
        }
        return mapping.get(source_type, ["baidu_news"])

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
    ) -> None:
        config = fetch_config or {}
        source_type = (source_type or "").strip()
        frequency = (fetch_frequency or "manual").strip()
        current_status = (status or "enabled").strip()
        visibility = (visibility_scope or "private").strip()
        if source_type not in self.allowed_source_types:
            raise ValueError(f"数据源类型不支持：{source_type or '未填写'}")
        if frequency not in self.allowed_fetch_frequencies:
            raise ValueError(f"抓取周期不支持：{frequency or '未填写'}")
        if current_status not in self.allowed_statuses:
            raise ValueError(f"数据源状态不支持：{current_status or '未填写'}")
        if visibility not in self.allowed_visibility_scopes:
            raise ValueError(f"可见范围不支持：{visibility or '未填写'}")

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
        return self._to_read(row, company)

    def _to_read(self, row: InsightDataSource, company: InsightCompany | None = None) -> InsightDataSourceRead:
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
