import re
from datetime import date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, exists, false, func, or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.agent.insight import (
    InsightCandidateReviewStatus,
    InsightCompany,
    InsightCrawlResult,
    InsightDataSource,
    InsightIntelligence,
    InsightIntelligenceCandidate,
    InsightIntelligenceSource,
    InsightReviewRecord,
    InsightTask,
    InsightUserIntelligencePool,
    InsightVisibilityRule,
    InsightVisibilityScope,
)
from app.schemas.agent.insight.dashboard import (
    InsightDashboardFocusItem,
    InsightDashboardMetric,
    InsightDashboardSourceSlice,
    InsightDashboardSummary,
    InsightDashboardTrendPoint,
)
from app.schemas.agent.insight.intelligence import (
    InsightCandidatePromoteRequest,
    InsightCandidateReviewRequest,
    InsightCandidateReviewResponse,
    InsightIntelligenceCandidateListItem,
    InsightIntelligenceCandidateRead,
    InsightIntelligenceCreate,
    InsightIntelligenceDetail,
    InsightIntelligenceListItem,
    InsightIntelligenceRead,
    InsightIntelligenceSourceCreate,
    InsightIntelligenceSourceRead,
    InsightIntelligenceUpdate,
    InsightPoolUpsertRequest,
    InsightUserIntelligencePoolRead,
    InsightVisibilityRuleCreate,
    InsightVisibilityRuleRead,
)
from app.models.agent.insight import InsightSubjectType
from app.schemas.page import Page
from app.services.agent.insight.permission_service import insight_permission_service


class InsightIntelligenceService:
    allowed_pool_types = {"favorite", "later", "hidden", "report_material"}

    async def get_dashboard(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightDashboardSummary:
        visible_ids = await self._get_dashboard_visible_intelligence_ids(db, user_id=user_id, is_admin=is_admin)
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=6)
        previous_week_start = today - timedelta(days=13)
        visible_items = await self._list_dashboard_intelligences(db, visible_ids)

        today_count = self._count_by_date(visible_items, today, today)
        yesterday_count = self._count_by_date(visible_items, yesterday, yesterday)
        week_focus_count = self._count_focus_items(visible_items, week_start, today)
        previous_week_focus_count = self._count_focus_items(visible_items, previous_week_start, week_start - timedelta(days=1))
        company_count = await self._count_dashboard_companies(db, user_id=user_id, is_admin=is_admin)
        data_source_count = await self._count_dashboard_data_sources(db)

        latest_items = await self._list_dashboard_latest_items(db, visible_ids, limit=8)
        focus_items = self._build_focus_items(visible_items, limit=5)
        trend = [
            InsightDashboardTrendPoint(
                date=day,
                label=day.strftime("%m-%d"),
                count=self._count_by_date(visible_items, day, day),
            )
            for day in (today - timedelta(days=offset) for offset in range(6, -1, -1))
        ]
        source_distribution = await self._build_source_distribution(db, visible_ids)
        return InsightDashboardSummary(
            metrics=[
                InsightDashboardMetric(
                    key="companies",
                    label="监控企业",
                    value=company_count,
                    compare_label="当前可见",
                    delta=0,
                ),
                InsightDashboardMetric(
                    key="data_sources",
                    label="数据源",
                    value=data_source_count,
                    compare_label="已启用",
                    delta=0,
                ),
                InsightDashboardMetric(
                    key="today_intelligence",
                    label="今日新增情报",
                    value=today_count,
                    compare_label="较昨日",
                    delta=today_count - yesterday_count,
                ),
                InsightDashboardMetric(
                    key="week_focus",
                    label="本周重点动态",
                    value=week_focus_count,
                    compare_label="较上周",
                    delta=week_focus_count - previous_week_focus_count,
                ),
            ],
            trend=trend,
            source_distribution=source_distribution,
            focus_items=focus_items,
            latest_items=latest_items,
        )

    async def create_intelligence(
        self,
        db: AsyncSession,
        payload: InsightIntelligenceCreate,
        user_id: int | None,
    ) -> InsightIntelligenceDetail:
        self._validate_intelligence_payload(payload)
        await self._ensure_data_source_reference_editable(
            db,
            payload.data_source_id,
            user_id=user_id,
            is_admin=False,
        )
        if payload.source:
            self._validate_source_payload(payload.source)
            await self._ensure_data_source_reference_editable(
                db,
                payload.source.data_source_id,
                user_id=user_id,
                is_admin=False,
            )
        intelligence = InsightIntelligence(
            intelligence_uid=f"intel_{uuid4().hex}",
            title=payload.title,
            summary=payload.summary,
            content=payload.content,
            company_id=payload.company_id,
            subject_type=InsightSubjectType(payload.subject_type),
            subject_id=payload.subject_id,
            subject_name=payload.subject_name,
            data_source_id=payload.data_source_id,
            intelligence_type=payload.intelligence_type,
            business_domain=payload.business_domain,
            importance_level=payload.importance_level,
            sentiment=payload.sentiment,
            publish_time=payload.publish_time,
            capture_time=datetime.now(),
            review_status="approved",
            review_user_id=user_id,
            review_time=datetime.now(),
            visibility_scope=InsightVisibilityScope(payload.visibility_scope),
            owner_user_id=user_id,
            raw_payload={"suggested_tags": payload.suggested_tags or [], "manual": True},
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(intelligence)
        await db.flush()
        source = None
        if payload.source:
            source = self._build_source_from_payload(intelligence.id or 0, payload.source)
            db.add(source)
        self._add_review_record(
            db,
            candidate_id=None,
            intelligence_id=intelligence.id,
            user_id=user_id,
            from_status=None,
            to_status="manual_created",
            review_comment="人工新增正式情报",
            diff_json={"action": "manual_create"},
        )
        await db.commit()
        await db.refresh(intelligence)
        sources = [source] if source else []
        return self._to_intelligence_detail(intelligence, sources)

    async def update_intelligence(
        self,
        db: AsyncSession,
        intelligence_id: int,
        payload: InsightIntelligenceUpdate,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightIntelligenceDetail:
        intelligence = await self._get_manageable_intelligence(db, intelligence_id, user_id=user_id, is_admin=is_admin)
        self._validate_intelligence_payload(payload)
        before = self._to_intelligence_read(intelligence).model_dump()
        data = payload.model_dump(exclude_unset=True)
        if "data_source_id" in data:
            await self._ensure_data_source_reference_editable(
                db,
                data.get("data_source_id"),
                user_id=user_id,
                is_admin=is_admin,
            )
        suggested_tags = data.pop("suggested_tags", None)
        if "subject_type" in data and data["subject_type"] is not None:
            data["subject_type"] = InsightSubjectType(data["subject_type"])
        if "visibility_scope" in data and data["visibility_scope"] is not None:
            data["visibility_scope"] = InsightVisibilityScope(data["visibility_scope"])
        for field, value in data.items():
            setattr(intelligence, field, value)
        if suggested_tags is not None:
            raw_payload = intelligence.raw_payload or {}
            raw_payload["suggested_tags"] = suggested_tags
            intelligence.raw_payload = raw_payload
        intelligence.update_time = datetime.now()
        intelligence.update_by = str(user_id) if user_id else None
        self._add_review_record(
            db,
            candidate_id=None,
            intelligence_id=intelligence.id,
            user_id=user_id,
            from_status=before.get("review_status"),
            to_status="manual_updated",
            review_comment="人工编辑正式情报",
            diff_json={"action": "manual_update", "fields": sorted(data.keys())},
        )
        await db.commit()
        await db.refresh(intelligence)
        sources = await self._list_sources(db, intelligence_id)
        return self._to_intelligence_detail(intelligence, sources)

    async def add_source(
        self,
        db: AsyncSession,
        intelligence_id: int,
        payload: InsightIntelligenceSourceCreate,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightIntelligenceSourceRead:
        await self._get_manageable_intelligence(db, intelligence_id, user_id=user_id, is_admin=is_admin)
        self._validate_source_payload(payload)
        await self._ensure_data_source_reference_editable(
            db,
            payload.data_source_id,
            user_id=user_id,
            is_admin=is_admin,
        )
        source = self._build_source_from_payload(intelligence_id, payload)
        source.create_by = str(user_id) if user_id else None
        source.update_by = str(user_id) if user_id else None
        db.add(source)
        self._add_review_record(
            db,
            candidate_id=None,
            intelligence_id=intelligence_id,
            user_id=user_id,
            from_status=None,
            to_status="source_added",
            review_comment="人工补充来源证据",
            diff_json={"action": "source_add", "source_type": payload.source_type},
        )
        await db.commit()
        await db.refresh(source)
        return self._to_source_read(source)

    async def list_intelligences(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None,
        subject_type: str | None,
        intelligence_type: str | None,
        visibility_scope: str | None,
        user_id: int | None,
        is_admin: bool,
    ) -> Page[InsightIntelligenceListItem]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightIntelligence.is_deleted == 0]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightIntelligence.title.ilike(like_keyword),
                    InsightIntelligence.summary.ilike(like_keyword),
                    InsightIntelligence.subject_name.ilike(like_keyword),
                )
            )
        if subject_type:
            filters.append(InsightIntelligence.subject_type == subject_type)
        if intelligence_type:
            filters.append(InsightIntelligence.intelligence_type == intelligence_type)
        if visibility_scope:
            filters.append(InsightIntelligence.visibility_scope == visibility_scope)
        if not is_admin:
            filters.append(
                or_(
                    await insight_permission_service.visibility_filter_for_user(
                        db,
                        InsightIntelligence,
                        target_type="intelligence",
                        user_id=user_id,
                        is_admin=is_admin,
                    ),
                    InsightIntelligence.review_user_id == user_id,
                )
            )
            hidden_ids = await self._get_user_pool_intelligence_ids(db, user_id=user_id, pool_type="hidden")
            if hidden_ids:
                filters.append(InsightIntelligence.id.notin_(hidden_ids))

        total_statement = select(func.count()).select_from(InsightIntelligence).where(*filters)
        total = (await db.exec(total_statement)).one()

        statement = (
            select(InsightIntelligence)
            .where(*filters)
            .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.create_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        intelligences = list((await db.exec(statement)).all())
        sources_by_intelligence = await self._list_sources_by_intelligence_ids(
            db,
            [item.id for item in intelligences if item.id],
        )
        items = [
            self._to_intelligence_list_item(item, sources_by_intelligence.get(item.id or 0, []))
            for item in intelligences
        ]
        return Page.create(items=items, total=total, page=page, size=size)

    async def get_intelligence_detail(
        self,
        db: AsyncSession,
        intelligence_id: int,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightIntelligenceDetail:
        filters = [
            InsightIntelligence.id == intelligence_id,
            InsightIntelligence.is_deleted == 0,
        ]
        if not is_admin:
            filters.append(
                or_(
                    await insight_permission_service.visibility_filter_for_user(
                        db,
                        InsightIntelligence,
                        target_type="intelligence",
                        user_id=user_id,
                        is_admin=is_admin,
                    ),
                    InsightIntelligence.review_user_id == user_id,
                )
            )
            hidden_ids = await self._get_user_pool_intelligence_ids(db, user_id=user_id, pool_type="hidden")
            if hidden_ids:
                filters.append(InsightIntelligence.id.notin_(hidden_ids))
        statement = select(InsightIntelligence).where(*filters)
        intelligence = (await db.exec(statement)).first()
        if not intelligence:
            raise ValueError("正式情报不存在或无权访问")
        sources = await self._list_sources(db, intelligence_id)
        return self._to_intelligence_detail(intelligence, sources)

    async def grant_visibility(
        self,
        db: AsyncSession,
        intelligence_id: int,
        payload: InsightVisibilityRuleCreate,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightVisibilityRuleRead:
        await self._get_manageable_intelligence(db, intelligence_id, user_id=user_id, is_admin=is_admin)
        rule = InsightVisibilityRule(
            target_type="intelligence",
            target_id=intelligence_id,
            principal_type=payload.principal_type,
            principal_id=payload.principal_id,
            permission=payload.permission,
            grant_type=payload.grant_type,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )
        db.add(rule)
        self._add_review_record(
            db,
            candidate_id=None,
            intelligence_id=intelligence_id,
            user_id=user_id,
            from_status=None,
            to_status="visibility_granted",
            review_comment="人工新增情报可见性授权",
            diff_json={"action": "visibility_grant", "principal_type": payload.principal_type, "principal_id": payload.principal_id},
        )
        await db.commit()
        await db.refresh(rule)
        return self._to_visibility_rule_read(rule)

    async def list_visibility_rules(
        self,
        db: AsyncSession,
        intelligence_id: int,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> list[InsightVisibilityRuleRead]:
        await self._get_manageable_intelligence(db, intelligence_id, user_id=user_id, is_admin=is_admin)
        statement = (
            select(InsightVisibilityRule)
            .where(
                InsightVisibilityRule.target_type == "intelligence",
                InsightVisibilityRule.target_id == intelligence_id,
                InsightVisibilityRule.is_deleted == 0,
            )
            .order_by(InsightVisibilityRule.create_time.desc())
        )
        return [self._to_visibility_rule_read(rule) for rule in (await db.exec(statement)).all()]

    async def upsert_user_pool(
        self,
        db: AsyncSession,
        intelligence_id: int,
        payload: InsightPoolUpsertRequest,
        *,
        user_id: int,
    ) -> InsightUserIntelligencePoolRead:
        if payload.pool_type not in self.allowed_pool_types:
            raise ValueError(f"情报池类型不支持：{payload.pool_type}")
        await self.get_intelligence_detail(db, intelligence_id, user_id=user_id, is_admin=False)
        statement = select(InsightUserIntelligencePool).where(
            InsightUserIntelligencePool.user_id == user_id,
            InsightUserIntelligencePool.intelligence_id == intelligence_id,
            InsightUserIntelligencePool.pool_type == payload.pool_type,
            InsightUserIntelligencePool.is_deleted == 0,
        )
        pool = (await db.exec(statement)).first()
        if pool:
            pool.folder_name = payload.folder_name
            pool.note = payload.note
            pool.status = "active"
            pool.update_time = datetime.now()
        else:
            pool = InsightUserIntelligencePool(
                user_id=user_id,
                intelligence_id=intelligence_id,
                pool_type=payload.pool_type,
                folder_name=payload.folder_name,
                note=payload.note,
                status="active",
            )
            db.add(pool)
        await db.commit()
        await db.refresh(pool)
        return self._to_pool_read(pool)

    async def remove_user_pool(
        self,
        db: AsyncSession,
        intelligence_id: int,
        pool_type: str,
        *,
        user_id: int,
    ) -> None:
        if pool_type not in self.allowed_pool_types:
            raise ValueError(f"情报池类型不支持：{pool_type}")
        statement = select(InsightUserIntelligencePool).where(
            InsightUserIntelligencePool.user_id == user_id,
            InsightUserIntelligencePool.intelligence_id == intelligence_id,
            InsightUserIntelligencePool.pool_type == pool_type,
            InsightUserIntelligencePool.is_deleted == 0,
        )
        pool = (await db.exec(statement)).first()
        if pool:
            pool.status = "inactive"
            pool.is_deleted = 1
            pool.update_time = datetime.now()
            await db.commit()

    async def list_user_pool(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        pool_type: str | None,
    ) -> list[InsightUserIntelligencePoolRead]:
        if pool_type and pool_type not in self.allowed_pool_types:
            raise ValueError(f"情报池类型不支持：{pool_type}")
        filters = [
            InsightUserIntelligencePool.user_id == user_id,
            InsightUserIntelligencePool.is_deleted == 0,
            InsightUserIntelligencePool.status == "active",
        ]
        if pool_type:
            filters.append(InsightUserIntelligencePool.pool_type == pool_type)
        statement = select(InsightUserIntelligencePool).where(*filters).order_by(InsightUserIntelligencePool.update_time.desc())
        return [self._to_pool_read(pool) for pool in (await db.exec(statement)).all()]

    async def list_candidates(
        self,
        db: AsyncSession,
        *,
        page: int,
        size: int,
        keyword: str | None,
        review_status: str | None,
        subject_type: str | None,
        intelligence_type: str | None,
        data_source_id: int | None,
        user_id: int | None,
        is_admin: bool,
    ) -> Page[InsightIntelligenceCandidateListItem]:
        page = max(page, 1)
        size = min(max(size, 1), 100)
        filters = [InsightIntelligenceCandidate.is_deleted == 0]
        crawl_filters = [InsightCrawlResult.is_deleted == 0]
        if keyword:
            like_keyword = f"%{keyword.strip()}%"
            filters.append(
                or_(
                    InsightIntelligenceCandidate.candidate_title.ilike(like_keyword),
                    InsightIntelligenceCandidate.candidate_summary.ilike(like_keyword),
                    InsightIntelligenceCandidate.subject_name.ilike(like_keyword),
                )
            )
        if review_status:
            filters.append(InsightIntelligenceCandidate.review_status == review_status)
        if subject_type:
            filters.append(InsightIntelligenceCandidate.subject_type == subject_type)
        if intelligence_type:
            filters.append(InsightIntelligenceCandidate.intelligence_type == intelligence_type)
        if data_source_id:
            crawl_filters.append(InsightCrawlResult.data_source_id == data_source_id)
        crawl_filters.append(
            await self._candidate_access_filter(
                db,
                user_id=user_id,
                is_admin=is_admin,
                permission="view",
            )
        )

        total_statement = (
            select(func.count())
            .select_from(InsightIntelligenceCandidate)
            .join(InsightCrawlResult, InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id)
            .where(*filters, *crawl_filters)
        )
        total = (await db.exec(total_statement)).one()

        statement = (
            select(InsightIntelligenceCandidate, InsightCrawlResult)
            .join(InsightCrawlResult, InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id)
            .where(*filters, *crawl_filters)
            .order_by(InsightIntelligenceCandidate.create_time.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await db.exec(statement)).all()
        items = [self._to_candidate_item(candidate, crawl_result) for candidate, crawl_result in rows]
        return Page.create(items=items, total=total, page=page, size=size)

    async def promote_candidate(
        self,
        db: AsyncSession,
        candidate_id: int | None,
        payload: InsightCandidatePromoteRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightCandidateReviewResponse:
        candidate, crawl_result = await self._get_candidate_with_crawl_result(
            db,
            candidate_id,
            user_id=user_id,
            is_admin=is_admin,
            permission="edit",
        )
        if candidate.review_status == InsightCandidateReviewStatus.PROMOTED and candidate.promoted_intelligence_id:
            intelligence = await self._get_intelligence(db, candidate.promoted_intelligence_id)
            return InsightCandidateReviewResponse(
                candidate=self._to_candidate_read(candidate),
                intelligence=self._to_intelligence_read(intelligence) if intelligence else None,
            )
        if candidate.review_status != InsightCandidateReviewStatus.PENDING:
            raise ValueError("候选情报已处理，不能重复审核")

        existing_intelligence = await self._get_existing_intelligence(db, crawl_result.dedupe_hash)
        if existing_intelligence:
            intelligence = existing_intelligence
        else:
            intelligence = self._build_intelligence(candidate, crawl_result, payload, user_id)
            db.add(intelligence)
            await db.flush()
            db.add(self._build_source(intelligence.id or 0, crawl_result))

        from_status = candidate.review_status.value
        candidate.review_status = InsightCandidateReviewStatus.PROMOTED
        candidate.promoted_intelligence_id = intelligence.id
        candidate.update_time = datetime.now()
        self._add_review_record(
            db,
            candidate_id=candidate.id or candidate_id,
            intelligence_id=intelligence.id,
            user_id=user_id,
            from_status=from_status,
            to_status=InsightCandidateReviewStatus.PROMOTED.value,
            review_comment=payload.review_comment,
            diff_json={"action": "promote", "deduped_intelligence": existing_intelligence is not None},
        )
        await db.commit()
        await db.refresh(candidate)
        await db.refresh(intelligence)
        return InsightCandidateReviewResponse(
            candidate=self._to_candidate_read(candidate),
            intelligence=self._to_intelligence_read(intelligence),
        )

    async def reject_candidate(
        self,
        db: AsyncSession,
        candidate_id: int,
        payload: InsightCandidateReviewRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightCandidateReviewResponse:
        return await self._change_candidate_status(
            db,
            candidate_id,
            InsightCandidateReviewStatus.REJECTED,
            payload,
            user_id,
            is_admin=is_admin,
        )

    async def ignore_candidate(
        self,
        db: AsyncSession,
        candidate_id: int,
        payload: InsightCandidateReviewRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightCandidateReviewResponse:
        return await self._change_candidate_status(
            db,
            candidate_id,
            InsightCandidateReviewStatus.IGNORED,
            payload,
            user_id,
            is_admin=is_admin,
        )

    async def _change_candidate_status(
        self,
        db: AsyncSession,
        candidate_id: int,
        to_status: InsightCandidateReviewStatus,
        payload: InsightCandidateReviewRequest,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> InsightCandidateReviewResponse:
        candidate, _ = await self._get_candidate_with_crawl_result(
            db,
            candidate_id,
            user_id=user_id,
            is_admin=is_admin,
            permission="edit",
        )
        if candidate.review_status != InsightCandidateReviewStatus.PENDING:
            raise ValueError("候选情报已处理，不能重复审核")
        from_status = candidate.review_status.value
        candidate.review_status = to_status
        candidate.update_time = datetime.now()
        self._add_review_record(
            db,
            candidate_id=candidate.id or candidate_id,
            intelligence_id=candidate.promoted_intelligence_id,
            user_id=user_id,
            from_status=from_status,
            to_status=to_status.value,
            review_comment=payload.review_comment,
            diff_json={"action": to_status.value},
        )
        await db.commit()
        await db.refresh(candidate)
        return InsightCandidateReviewResponse(candidate=self._to_candidate_read(candidate), intelligence=None)

    async def _get_candidate_with_crawl_result(
        self,
        db: AsyncSession,
        candidate_id: int,
        *,
        user_id: int | None,
        is_admin: bool,
        permission: str = "view",
    ) -> tuple[InsightIntelligenceCandidate, InsightCrawlResult]:
        statement = (
            select(InsightIntelligenceCandidate, InsightCrawlResult)
            .join(InsightCrawlResult, InsightCrawlResult.id == InsightIntelligenceCandidate.crawl_result_id)
            .where(
                InsightIntelligenceCandidate.id == candidate_id,
                InsightIntelligenceCandidate.is_deleted == 0,
                InsightCrawlResult.is_deleted == 0,
                await self._candidate_access_filter(
                    db,
                    user_id=user_id,
                    is_admin=is_admin,
                    permission=permission,
                ),
            )
        )
        row = (await db.exec(statement)).first()
        if not row:
            raise ValueError("候选情报不存在")
        return row

    async def _candidate_access_filter(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
        permission: str = "view",
    ):
        if is_admin:
            return True
        if not user_id:
            return false()
        data_source_filter = await insight_permission_service.visibility_filter_for_user(
            db,
            InsightDataSource,
            target_type="data_source",
            user_id=user_id,
            is_admin=False,
            permission=permission,
        )
        task_owner_filter = (
            exists()
            .where(
                InsightTask.id == InsightCrawlResult.task_id,
                InsightTask.is_deleted == 0,
                InsightTask.create_by == str(user_id),
            )
            .correlate(InsightCrawlResult)
        )
        return or_(
            exists()
            .where(
                InsightDataSource.id == InsightCrawlResult.data_source_id,
                InsightDataSource.is_deleted == 0,
                data_source_filter,
            )
            .correlate(InsightCrawlResult),
            and_(
                InsightCrawlResult.data_source_id.is_(None),
                task_owner_filter,
            ),
        )

    async def _get_intelligence(self, db: AsyncSession, intelligence_id: int) -> InsightIntelligence | None:
        statement = select(InsightIntelligence).where(
            InsightIntelligence.id == intelligence_id,
            InsightIntelligence.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    async def _get_manageable_intelligence(
        self,
        db: AsyncSession,
        intelligence_id: int,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> InsightIntelligence:
        filters = [
            InsightIntelligence.id == intelligence_id,
            InsightIntelligence.is_deleted == 0,
        ]
        if not is_admin:
            filters.append(
                or_(
                    InsightIntelligence.owner_user_id == user_id,
                    InsightIntelligence.review_user_id == user_id,
                    await insight_permission_service.visibility_filter_for_user(
                        db,
                        InsightIntelligence,
                        target_type="intelligence",
                        user_id=user_id,
                        is_admin=is_admin,
                        permission="edit",
                    ),
                )
            )
        statement = select(InsightIntelligence).where(*filters)
        intelligence = (await db.exec(statement)).first()
        if not intelligence:
            raise ValueError("正式情报不存在或无权维护")
        return intelligence

    async def _ensure_data_source_reference_editable(
        self,
        db: AsyncSession,
        data_source_id: int | None,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> None:
        if not data_source_id or is_admin:
            return
        statement = select(InsightDataSource).where(
            InsightDataSource.id == data_source_id,
            InsightDataSource.is_deleted == 0,
            await insight_permission_service.visibility_filter_for_user(
                db,
                InsightDataSource,
                target_type="data_source",
                user_id=user_id,
                is_admin=is_admin,
                permission="edit",
            ),
        )
        if not (await db.exec(statement)).first():
            raise ValueError("关联数据源不存在或无权维护")

    def _validate_intelligence_payload(self, payload: InsightIntelligenceCreate | InsightIntelligenceUpdate) -> None:
        title = getattr(payload, "title", None)
        if title is not None and not title.strip():
            raise ValueError("正式情报标题不能为空")

    def _validate_source_payload(self, payload: InsightIntelligenceSourceCreate) -> None:
        if not any(
            str(value or "").strip()
            for value in (
                payload.source_url,
                payload.source_title,
                payload.content_excerpt,
                payload.file_object_path,
            )
        ):
            raise ValueError("来源证据至少需要填写 URL、标题、摘录或文件路径之一")

    async def _get_visible_intelligence_ids(self, db: AsyncSession, user_id: int | None) -> list[int]:
        return await insight_permission_service.visible_target_ids_for_user(
            db,
            target_type="intelligence",
            user_id=user_id,
        )

    async def _get_user_pool_intelligence_ids(self, db: AsyncSession, user_id: int | None, pool_type: str) -> list[int]:
        if not user_id:
            return []
        statement = select(InsightUserIntelligencePool.intelligence_id).where(
            InsightUserIntelligencePool.user_id == user_id,
            InsightUserIntelligencePool.pool_type == pool_type,
            InsightUserIntelligencePool.status == "active",
            InsightUserIntelligencePool.is_deleted == 0,
        )
        return list((await db.exec(statement)).all())

    async def _get_existing_intelligence(self, db: AsyncSession, dedupe_hash: str | None) -> InsightIntelligence | None:
        if not dedupe_hash:
            return None
        statement = select(InsightIntelligence).where(
            InsightIntelligence.dedupe_hash == dedupe_hash,
            InsightIntelligence.is_deleted == 0,
        )
        return (await db.exec(statement)).first()

    async def _get_dashboard_visible_intelligence_ids(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> list[int]:
        filters = [InsightIntelligence.is_deleted == 0, InsightIntelligence.status == "active"]
        if not is_admin:
            granted_ids = await self._get_visible_intelligence_ids(db, user_id=user_id)
            filters.append(
                or_(
                    InsightIntelligence.visibility_scope == InsightVisibilityScope.PUBLIC,
                    InsightIntelligence.owner_user_id == user_id,
                    InsightIntelligence.review_user_id == user_id,
                    InsightIntelligence.id.in_(granted_ids) if granted_ids else False,
                )
            )
            hidden_ids = await self._get_user_pool_intelligence_ids(db, user_id=user_id, pool_type="hidden")
            if hidden_ids:
                filters.append(InsightIntelligence.id.notin_(hidden_ids))
        statement = select(InsightIntelligence.id).where(*filters)
        return list((await db.exec(statement)).all())

    async def _list_dashboard_intelligences(
        self,
        db: AsyncSession,
        intelligence_ids: list[int],
    ) -> list[InsightIntelligence]:
        if not intelligence_ids:
            return []
        statement = select(InsightIntelligence).where(
            InsightIntelligence.id.in_(intelligence_ids),
            InsightIntelligence.is_deleted == 0,
        )
        return list((await db.exec(statement)).all())

    async def _list_dashboard_latest_items(
        self,
        db: AsyncSession,
        intelligence_ids: list[int],
        *,
        limit: int,
    ) -> list[InsightIntelligenceListItem]:
        if not intelligence_ids:
            return []
        statement = (
            select(InsightIntelligence)
            .where(
                InsightIntelligence.id.in_(intelligence_ids),
                InsightIntelligence.is_deleted == 0,
            )
            .order_by(InsightIntelligence.publish_time.desc().nullslast(), InsightIntelligence.create_time.desc())
            .limit(limit)
        )
        intelligences = list((await db.exec(statement)).all())
        sources_by_intelligence = await self._list_sources_by_intelligence_ids(
            db,
            [item.id for item in intelligences if item.id],
        )
        return [
            self._to_intelligence_list_item(item, sources_by_intelligence.get(item.id or 0, []))
            for item in intelligences
        ]

    async def _count_dashboard_companies(
        self,
        db: AsyncSession,
        *,
        user_id: int | None,
        is_admin: bool,
    ) -> int:
        filters = [InsightCompany.is_deleted == 0, InsightCompany.status == "active"]
        if not is_admin:
            filters.append(InsightCompany.owner_user_id == user_id)
        statement = select(func.count()).select_from(InsightCompany).where(*filters)
        return (await db.exec(statement)).one()

    async def _count_dashboard_data_sources(self, db: AsyncSession) -> int:
        statement = select(func.count()).select_from(InsightDataSource).where(
            InsightDataSource.is_deleted == 0,
            InsightDataSource.status == "enabled",
        )
        return (await db.exec(statement)).one()

    async def _build_source_distribution(
        self,
        db: AsyncSession,
        intelligence_ids: list[int],
    ) -> list[InsightDashboardSourceSlice]:
        if not intelligence_ids:
            return []
        statement = (
            select(InsightIntelligenceSource.source_type, func.count())
            .where(
                InsightIntelligenceSource.intelligence_id.in_(intelligence_ids),
                InsightIntelligenceSource.is_deleted == 0,
            )
            .group_by(InsightIntelligenceSource.source_type)
            .order_by(func.count().desc())
            .limit(6)
        )
        rows = list((await db.exec(statement)).all())
        total = sum(row[1] for row in rows)
        if total <= 0:
            return []
        return [
            InsightDashboardSourceSlice(
                source_type=row[0],
                label=self._source_type_label(row[0]),
                count=row[1],
                percent=round(row[1] * 100 / total, 1),
            )
            for row in rows
        ]

    def _build_focus_items(
        self,
        intelligences: list[InsightIntelligence],
        *,
        limit: int,
    ) -> list[InsightDashboardFocusItem]:
        sorted_items = sorted(intelligences, key=self._focus_score, reverse=True)
        return [
            InsightDashboardFocusItem(
                id=item.id or 0,
                title=item.title,
                subject_name=item.subject_name,
                intelligence_type=item.intelligence_type,
                importance_level=item.importance_level,
                publish_time=item.publish_time or item.create_time,
                score=self._focus_score(item),
            )
            for item in sorted_items[:limit]
        ]

    def _focus_score(self, intelligence: InsightIntelligence) -> int:
        importance_scores = {"high": 80, "medium": 50, "low": 20}
        score = importance_scores.get(intelligence.importance_level, 40)
        event_time = intelligence.publish_time or intelligence.create_time
        age_days = max((datetime.now() - event_time).days, 0)
        score += max(20 - age_days * 2, 0)
        if intelligence.sentiment and intelligence.sentiment != "neutral":
            score += 6
        return score

    def _count_focus_items(
        self,
        intelligences: list[InsightIntelligence],
        start_date: date,
        end_date: date,
    ) -> int:
        return sum(
            1
            for item in intelligences
            if item.importance_level == "high" and self._is_in_date_range(item.publish_time or item.create_time, start_date, end_date)
        )

    def _count_by_date(
        self,
        intelligences: list[InsightIntelligence],
        start_date: date,
        end_date: date,
    ) -> int:
        return sum(
            1
            for item in intelligences
            if self._is_in_date_range(item.publish_time or item.create_time, start_date, end_date)
        )

    def _is_in_date_range(self, value: datetime, start_date: date, end_date: date) -> bool:
        current_date = value.date()
        return start_date <= current_date <= end_date

    def _source_type_label(self, source_type: str) -> str:
        labels = {
            "baidu": "百度搜索",
            "bocha": "博查搜索",
            "firecrawl": "网页抓取",
            "manual": "人工录入",
            "official": "官网",
            "financial_report": "财报公告",
            "industry_news": "行业资讯",
            "wechat": "公众号",
        }
        return labels.get(source_type, source_type or "其他来源")

    async def _list_sources_by_intelligence_ids(
        self,
        db: AsyncSession,
        intelligence_ids: list[int],
    ) -> dict[int, list[InsightIntelligenceSource]]:
        if not intelligence_ids:
            return {}
        statement = (
            select(InsightIntelligenceSource)
            .where(
                InsightIntelligenceSource.intelligence_id.in_(intelligence_ids),
                InsightIntelligenceSource.is_deleted == 0,
            )
            .order_by(InsightIntelligenceSource.create_time.asc())
        )
        sources = list((await db.exec(statement)).all())
        result: dict[int, list[InsightIntelligenceSource]] = {}
        for source in sources:
            result.setdefault(source.intelligence_id, []).append(source)
        return result

    async def _list_sources(self, db: AsyncSession, intelligence_id: int) -> list[InsightIntelligenceSource]:
        statement = (
            select(InsightIntelligenceSource)
            .where(
                InsightIntelligenceSource.intelligence_id == intelligence_id,
                InsightIntelligenceSource.is_deleted == 0,
            )
            .order_by(InsightIntelligenceSource.create_time.asc())
        )
        return list((await db.exec(statement)).all())

    def _build_intelligence(
        self,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
        payload: InsightCandidatePromoteRequest,
        user_id: int | None,
    ) -> InsightIntelligence:
        now = datetime.now()
        return InsightIntelligence(
            intelligence_uid=f"intel_{uuid4().hex}",
            title=candidate.candidate_title,
            summary=candidate.candidate_summary,
            content=crawl_result.markdown_content,
            company_id=candidate.company_id,
            subject_type=candidate.subject_type,
            subject_name=candidate.subject_name,
            data_source_id=crawl_result.data_source_id,
            intelligence_type=self._normalize_intelligence_type(candidate.intelligence_type),
            business_domain=payload.business_domain,
            importance_level=payload.importance_level,
            sentiment="neutral",
            publish_time=crawl_result.published_at,
            capture_time=crawl_result.create_time,
            review_status="approved",
            review_user_id=user_id,
            review_time=now,
            dedupe_hash=crawl_result.dedupe_hash,
            visibility_scope=InsightVisibilityScope(payload.visibility_scope),
            owner_user_id=user_id,
            raw_payload={
                "candidate_id": candidate.id,
                "crawl_result_id": crawl_result.id,
                "suggested_tags": candidate.suggested_tags,
                "confidence": candidate.confidence,
            },
            status="active",
            create_by=str(user_id) if user_id else None,
            update_by=str(user_id) if user_id else None,
        )

    def _build_source(self, intelligence_id: int, crawl_result: InsightCrawlResult) -> InsightIntelligenceSource:
        return InsightIntelligenceSource(
            intelligence_id=intelligence_id,
            data_source_id=crawl_result.data_source_id,
            source_type=crawl_result.channel.value,
            source_url=crawl_result.source_url,
            source_title=crawl_result.source_title,
            source_publish_time=crawl_result.published_at,
            content_excerpt=crawl_result.snippet,
            credibility_score=0.7,
            source_metadata=crawl_result.crawl_metadata,
        )

    def _build_source_from_payload(
        self,
        intelligence_id: int,
        payload: InsightIntelligenceSourceCreate,
    ) -> InsightIntelligenceSource:
        return InsightIntelligenceSource(
            intelligence_id=intelligence_id,
            data_source_id=payload.data_source_id,
            source_type=payload.source_type,
            source_url=payload.source_url,
            source_title=payload.source_title,
            source_author=payload.source_author,
            source_publish_time=payload.source_publish_time,
            content_excerpt=payload.content_excerpt,
            file_object_path=payload.file_object_path,
            credibility_score=payload.credibility_score,
            source_metadata=payload.source_metadata,
        )

    def _add_review_record(
        self,
        db: AsyncSession,
        *,
        candidate_id: int,
        intelligence_id: int | None,
        user_id: int | None,
        from_status: str | None,
        to_status: str,
        review_comment: str | None,
        diff_json: dict[str, object],
    ) -> None:
        db.add(
            InsightReviewRecord(
                intelligence_id=intelligence_id,
                candidate_id=candidate_id,
                review_user_id=user_id,
                from_status=from_status,
                to_status=to_status,
                review_comment=review_comment,
                diff_json=diff_json,
            )
        )

    def _to_candidate_item(
        self,
        candidate: InsightIntelligenceCandidate,
        crawl_result: InsightCrawlResult,
    ) -> InsightIntelligenceCandidateListItem:
        quality_report = self._candidate_quality_report(crawl_result)
        return InsightIntelligenceCandidateListItem(
            id=candidate.id,
            create_time=candidate.create_time,
            update_time=candidate.update_time,
            create_by=candidate.create_by,
            update_by=candidate.update_by,
            comment=candidate.comment,
            is_deleted=candidate.is_deleted,
            crawl_result_id=candidate.crawl_result_id,
            candidate_title=candidate.candidate_title,
            candidate_summary=candidate.candidate_summary,
            subject_type=candidate.subject_type.value,
            subject_name=candidate.subject_name,
            company_id=candidate.company_id,
            intelligence_type=self._normalize_intelligence_type(candidate.intelligence_type),
            suggested_tags=candidate.suggested_tags,
            quality_report=quality_report,
            quality_score=self._quality_score(quality_report),
            quality_issues=self._quality_issues(quality_report),
            quality_auto_ignore=bool(quality_report.get("auto_ignore")) if quality_report else False,
            confidence=candidate.confidence,
            promoted_intelligence_id=candidate.promoted_intelligence_id,
            review_status=candidate.review_status.value,
            status=candidate.status,
            source_url=crawl_result.source_url,
            source_title=crawl_result.source_title,
            source_channel=crawl_result.channel.value,
            source_publish_time=crawl_result.published_at,
            query_text=crawl_result.query_text,
        )

    def _to_candidate_read(self, candidate: InsightIntelligenceCandidate) -> InsightIntelligenceCandidateRead:
        quality_report = self._candidate_quality_report_from_tags(candidate.suggested_tags)
        return InsightIntelligenceCandidateRead(
            id=candidate.id,
            create_time=candidate.create_time,
            update_time=candidate.update_time,
            create_by=candidate.create_by,
            update_by=candidate.update_by,
            comment=candidate.comment,
            is_deleted=candidate.is_deleted,
            crawl_result_id=candidate.crawl_result_id,
            candidate_title=candidate.candidate_title,
            candidate_summary=candidate.candidate_summary,
            subject_type=candidate.subject_type.value,
            subject_name=candidate.subject_name,
            company_id=candidate.company_id,
            intelligence_type=self._normalize_intelligence_type(candidate.intelligence_type),
            suggested_tags=candidate.suggested_tags,
            quality_report=quality_report,
            quality_score=self._quality_score(quality_report),
            quality_issues=self._quality_issues(quality_report),
            quality_auto_ignore=bool(quality_report.get("auto_ignore")) if quality_report else False,
            confidence=candidate.confidence,
            promoted_intelligence_id=candidate.promoted_intelligence_id,
            review_status=candidate.review_status.value,
            status=candidate.status,
        )

    def _candidate_quality_report(self, crawl_result: InsightCrawlResult) -> dict[str, object] | None:
        metadata = crawl_result.crawl_metadata or {}
        value = metadata.get("quality_report") if isinstance(metadata, dict) else None
        return value if isinstance(value, dict) else None

    def _candidate_quality_report_from_tags(self, tags: object) -> dict[str, object] | None:
        issues = [
            str(item.get("name")).strip()
            for item in tags
            if isinstance(item, dict) and item.get("source") == "quality_rule" and str(item.get("name") or "").strip()
        ] if isinstance(tags, list) else []
        if not issues:
            return None
        return {
            "issues": issues,
            "auto_ignore": any("忽略" in issue or "ignore" in issue.lower() for issue in issues),
        }

    def _quality_score(self, quality_report: dict[str, object] | None) -> float | None:
        if not quality_report or quality_report.get("score") is None:
            return None
        try:
            return float(quality_report["score"])
        except (TypeError, ValueError):
            return None

    def _quality_issues(self, quality_report: dict[str, object] | None) -> list[str]:
        if not quality_report:
            return []
        raw_issues = quality_report.get("issues")
        return [str(item) for item in raw_issues if str(item).strip()] if isinstance(raw_issues, list) else []

    def _to_intelligence_read(self, intelligence: InsightIntelligence) -> InsightIntelligenceRead:
        return InsightIntelligenceRead(
            id=intelligence.id,
            create_time=intelligence.create_time,
            update_time=intelligence.update_time,
            create_by=intelligence.create_by,
            update_by=intelligence.update_by,
            comment=intelligence.comment,
            is_deleted=intelligence.is_deleted,
            intelligence_uid=intelligence.intelligence_uid,
            title=intelligence.title,
            summary=intelligence.summary,
            company_id=intelligence.company_id,
            subject_type=intelligence.subject_type.value,
            subject_id=intelligence.subject_id,
            subject_name=intelligence.subject_name,
            intelligence_type=self._normalize_intelligence_type(intelligence.intelligence_type),
            business_domain=intelligence.business_domain,
            importance_level=intelligence.importance_level,
            sentiment=intelligence.sentiment,
            publish_time=intelligence.publish_time,
            capture_time=intelligence.capture_time,
            review_status=intelligence.review_status,
            visibility_scope=intelligence.visibility_scope.value,
            status=intelligence.status,
        )

    def _to_intelligence_list_item(
        self,
        intelligence: InsightIntelligence,
        sources: list[InsightIntelligenceSource],
    ) -> InsightIntelligenceListItem:
        primary_source = sources[0] if sources else None
        raw_payload = intelligence.raw_payload or {}
        return InsightIntelligenceListItem(
            **self._to_intelligence_read(intelligence).model_dump(),
            primary_source_url=primary_source.source_url if primary_source else None,
            primary_source_title=primary_source.source_title if primary_source else None,
            primary_source_type=primary_source.source_type if primary_source else None,
            source_count=len(sources),
            suggested_tags=raw_payload.get("suggested_tags") if isinstance(raw_payload, dict) else None,
        )

    def _normalize_intelligence_type(self, value: object) -> str:
        text = str(value or "").strip()
        mapping = {
            "strategic_planning": "战略规划",
            "strategy": "战略规划",
            "marketing_strategy": "营销策略",
            "competitor_strategy": "竞品动态",
            "competitor": "竞品动态",
            "product_launch": "新品情报",
            "product_launch_failure": "新品情报",
            "new_product": "新品情报",
            "financial_report": "财报公告",
            "financial": "财报公告",
            "industry_news": "行业资讯",
            "industry": "行业资讯",
            "policy": "政策法规",
            "regulation": "政策法规",
            "application_solution": "应用方案",
            "technology": "应用方案",
            "business_operation": "经营动态",
            "operation": "经营动态",
            "risk_warning": "风险预警",
            "risk": "风险预警",
        }
        normalized = text.lower().replace("-", "_").replace(" ", "_")
        if normalized in mapping:
            return mapping[normalized]
        if re.fullmatch(r"[A-Za-z0-9_]+", text):
            return "行业资讯"
        return text[:50] if text else "行业资讯"

    def _to_intelligence_detail(
        self,
        intelligence: InsightIntelligence,
        sources: list[InsightIntelligenceSource],
    ) -> InsightIntelligenceDetail:
        return InsightIntelligenceDetail(
            **self._to_intelligence_read(intelligence).model_dump(),
            content=intelligence.content,
            raw_payload=intelligence.raw_payload,
            sources=[self._to_source_read(source) for source in sources],
        )

    def _to_source_read(self, source: InsightIntelligenceSource) -> InsightIntelligenceSourceRead:
        return InsightIntelligenceSourceRead(
            id=source.id,
            create_time=source.create_time,
            update_time=source.update_time,
            create_by=source.create_by,
            update_by=source.update_by,
            comment=source.comment,
            is_deleted=source.is_deleted,
            intelligence_id=source.intelligence_id,
            data_source_id=source.data_source_id,
            source_type=source.source_type,
            source_url=source.source_url,
            source_title=source.source_title,
            source_author=source.source_author,
            source_publish_time=source.source_publish_time,
            content_excerpt=source.content_excerpt,
            file_object_path=source.file_object_path,
            credibility_score=source.credibility_score,
            source_metadata=source.source_metadata,
        )

    def _to_visibility_rule_read(self, rule: InsightVisibilityRule) -> InsightVisibilityRuleRead:
        return InsightVisibilityRuleRead(
            id=rule.id,
            create_time=rule.create_time,
            update_time=rule.update_time,
            create_by=rule.create_by,
            update_by=rule.update_by,
            comment=rule.comment,
            is_deleted=rule.is_deleted,
            target_type=rule.target_type,
            target_id=rule.target_id,
            principal_type=rule.principal_type,
            principal_id=rule.principal_id,
            permission=rule.permission,
            grant_type=rule.grant_type,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            status=rule.status,
        )

    def _to_pool_read(self, pool: InsightUserIntelligencePool) -> InsightUserIntelligencePoolRead:
        return InsightUserIntelligencePoolRead(
            id=pool.id,
            create_time=pool.create_time,
            update_time=pool.update_time,
            create_by=pool.create_by,
            update_by=pool.update_by,
            comment=pool.comment,
            is_deleted=pool.is_deleted,
            user_id=pool.user_id,
            intelligence_id=pool.intelligence_id,
            pool_type=pool.pool_type,
            folder_name=pool.folder_name,
            note=pool.note,
            sort_no=pool.sort_no,
            status=pool.status,
        )


insight_intelligence_service = InsightIntelligenceService()
